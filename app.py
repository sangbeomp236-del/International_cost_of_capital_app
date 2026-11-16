import io
import re
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide"
)

# --------------------------------------------------
# Source URLs
# --------------------------------------------------

BETAS_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"

RATINGS_URL = (
    "https://pages.stern.nyu.edu/adamodar/"
    "New_Home_Page/datafile/ratings.html"
)

OECD_XLSX_URL = "https://stat.link/0qkxo1"

OECD_PAGE = (
    "https://www.oecd.org/en/publications/"
    "corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_"
    "440f9286.html"
)

TE_URL = "https://tradingeconomics.com/bonds"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_ERP = 0.065
DEFAULT_DEBT = 0.30


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def get(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=25
    )
    r.raise_for_status()
    return r


def norm_country(x):

    x = re.sub(
        r"\s+",
        " ",
        str(x)
    ).strip()

    aliases = {
        "USA": "United States",
        "US": "United States",
        "Korea": "South Korea",
        "Republic of Korea": "South Korea",
        "Türkiye": "Turkey",
        "Viet Nam": "Vietnam",
        "China (People's Republic of)": "China",
        "Russian Federation": "Russia",
    }

    return aliases.get(x, x)


def to_rate(x):

    if pd.isna(x):
        return None

    s = str(x).replace(",", "").strip()

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        s
    )

    if not m:
        return None

    v = float(m.group())

    if "%" in s or abs(v) > 1:
        v /= 100

    return v


# --------------------------------------------------
# Fetch industry betas
# --------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_betas():

    content = get(BETAS_URL).content

    raw = pd.read_excel(
        io.BytesIO(content),
        header=None
    )

    header_row = None

    for i in range(min(40, len(raw))):

        line = " | ".join(
            raw.iloc[i].astype(str)
        ).lower()

        if (
            "industry" in line
            and "unlevered beta" in line
        ):
            header_row = i
            break

    if header_row is None:

        raise ValueError(
            "Could not find the header row "
            "in Damodaran beta file."
        )

    df = pd.read_excel(
        io.BytesIO(content),
        header=header_row
    )

    df.columns = [
        str(c).strip()
        for c in df.columns
    ]

    industry_col = next(
        c
        for c in df.columns
        if "industry" in c.lower()
    )

    beta_col = next(
        c
        for c in df.columns
        if (
            "unlevered beta" in c.lower()
            and "cash" not in c.lower()
        )
    )

    out = df[
        [
            industry_col,
            beta_col
        ]
    ].copy()

    out.columns = [
        "Industry",
        "Unlevered Beta"
    ]

    out["Industry"] = (
        out["Industry"]
        .astype(str)
        .str.strip()
    )

    out["Unlevered Beta"] = (
        pd.to_numeric(
            out["Unlevered Beta"],
            errors="coerce"
        )
    )

    out = (
        out
        .dropna()
        .drop_duplicates("Industry")
    )

    return out.sort_values(
        "Industry"
    )


# --------------------------------------------------
# Fetch BBB spread
# --------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_bbb_spread():

    html = get(RATINGS_URL).text

    tables = pd.read_html(
        io.StringIO(html)
    )

    for table in tables:

        for _, row in table.iterrows():

            vals = [
                str(v)
                for v in row.tolist()
            ]

            if any(
                "Baa2/BBB" in v
                for v in vals
            ):

                idx = next(
                    i
                    for i, v in enumerate(vals)
                    if "Baa2/BBB" in v
                )

                for v in vals[idx + 1:]:

                    rate = to_rate(v)

                    if (
                        rate is not None
                        and 0 < rate < 0.20
                    ):
                        return rate

    # Current Damodaran fallback value
    return 0.0111


# --------------------------------------------------
# Fetch OECD corporate tax rates
# --------------------------------------------------

@st.cache_data(ttl=86400)
def fetch_tax_rates():

    content = get(
        OECD_XLSX_URL
    ).content

    sheets = pd.read_excel(
        io.BytesIO(content),
        sheet_name=None,
        header=None
    )

    rates = {}

    ignore = (
        "source",
        "note",
        "figure",
        "average",
        "statutory",
        "corporate",
        "jurisdiction",
    )

    for df in sheets.values():

        for _, row in df.iterrows():

            vals = [
                v
                for v in row.tolist()
                if not pd.isna(v)
            ]

            names = [
                str(v).strip()
                for v in vals
                if isinstance(v, str)
            ]

            nums = [
                float(v)
                for v in vals
                if isinstance(v, (int, float))
                and 0 <= float(v) <= 100
            ]

            if not names or not nums:
                continue

            country = names[0]

            if any(
                k in country.lower()
                for k in ignore
            ):
                continue

            if len(country) > 60:
                continue

            value = nums[-1]

            rate = (
                value
                if value <= 1
                else value / 100
            )

            if 0 <= rate <= 0.60:

                rates[
                    norm_country(country)
                ] = rate

    if len(rates) < 20:

        raise ValueError(
            "OECD tax table "
            "could not be parsed."
        )

    return rates


# --------------------------------------------------
# Fetch government yields
# --------------------------------------------------

@st.cache_data(ttl=1800)
def fetch_yields():

    html = get(TE_URL).text

    tables = pd.read_html(
        io.StringIO(html)
    )

    rates = {}

    for df in tables:

        if (
            df.empty
            or len(df.columns) < 2
        ):
            continue

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        country_col = next(
            (
                c
                for c in df.columns
                if "country" in c.lower()
            ),
            df.columns[0]
        )

        value_col = next(
            (
                c
                for c in df.columns
                if c.lower() in {
                    "yield",
                    "last"
                }
            ),
            None
        )

        if value_col is None:
            value_col = df.columns[1]

        for _, row in df.iterrows():

            country = norm_country(
                row[country_col]
            )

            y = to_rate(
                row[value_col]
            )

            if (
                country
                and y is not None
                and -0.05 < y < 0.50
            ):

                rates[country] = y

    if "United States" not in rates:

        raise ValueError(
            "Trading Economics table "
            "could not be parsed."
        )

    return rates


# --------------------------------------------------
# Finance formulas
# --------------------------------------------------

def relever(
    beta_u,
    tax,
    debt_share
):

    if debt_share == 0:
        return beta_u

    de = (
        debt_share
        / (1 - debt_share)
    )

    return (
        beta_u
        * (
            1
            + (1 - tax) * de
        )
    )


def calc(
    beta_u,
    tax,
    erp,
    debt_share,
    y_us,
    y_foreign,
    spread_us,
    spread_foreign_override=None
):

    beta_l = relever(
        beta_u,
        tax,
        debt_share
    )

    # USD cost of equity
    ke_us = (
        y_us
        + beta_l * erp
    )

    # USD debt cost
    kd_us_pre = (
        y_us
        + spread_us
    )

    kd_us_after = (
        kd_us_pre
        * (1 - tax)
    )

    wacc_us = (
        (1 - debt_share) * ke_us
        + debt_share * kd_us_after
    )

    # Currency adjustment
    currency_factor = (
        (1 + y_foreign)
        / (1 + y_us)
    )

    # Foreign currency cost of equity
    ke_foreign = (
        (1 + ke_us)
        * currency_factor
        - 1
    )

    # Foreign currency debt cost
    if spread_foreign_override is None:

        kd_foreign_pre = (
            (1 + kd_us_pre)
            * currency_factor
            - 1
        )

        spread_foreign = (
            kd_foreign_pre
            - y_foreign
        )

    else:

        spread_foreign = (
            spread_foreign_override
        )

        kd_foreign_pre = (
            y_foreign
            + spread_foreign
        )

    kd_foreign_after = (
        kd_foreign_pre
        * (1 - tax)
    )

    wacc_foreign = (
        (1 - debt_share)
        * ke_foreign
        + debt_share
        * kd_foreign_after
    )

    return {

        "beta_l": beta_l,

        "ke_us": ke_us,

        "kd_us_pre": kd_us_pre,

        "kd_us_after": kd_us_after,

        "wacc_us": wacc_us,

        "ke_foreign": ke_foreign,

        "spread_foreign": spread_foreign,

        "kd_foreign_pre": kd_foreign_pre,

        "kd_foreign_after": kd_foreign_after,

        "wacc_foreign": wacc_foreign,
    }


def pct(x):

    return f"{x * 100:.2f}%"


# --------------------------------------------------
# Page title
# --------------------------------------------------

st.title(
    "🌍 International Cost of Capital"
)

st.caption(
    "Compare a project's cost of equity "
    "and WACC in USD and in a selected "
    "country's currency."
)


# --------------------------------------------------
# Refresh data
# --------------------------------------------------

if st.button(
    "🔄 Refresh source data"
):

    st.cache_data.clear()

    st.rerun()


# --------------------------------------------------
# Load data
# --------------------------------------------------

errors = []

try:

    betas = fetch_betas()

except Exception as e:

    betas = pd.DataFrame(
        {
            "Industry": [
                DEFAULT_INDUSTRY
            ],
            "Unlevered Beta": [
                1.23
            ]
        }
    )

    errors.append(
        f"Damodaran beta fetch failed: {e}"
    )


try:

    bbb = fetch_bbb_spread()

except Exception as e:

    bbb = 0.0111

    errors.append(
        f"Damodaran BBB spread fetch failed: {e}"
    )


try:

    taxes = fetch_tax_rates()

except Exception as e:

    taxes = {
        "United States": 0.256,
        "Colombia": 0.35,
    }

    errors.append(
        f"OECD tax fetch failed: {e}"
    )


try:

    yields = fetch_yields()

except Exception as e:

    yields = {
        "United States": 0.04
    }

    errors.append(
        f"Trading Economics yield fetch failed: {e}"
    )


for msg in errors:

    st.warning(
        msg
        + " — use the manual override if needed."
    )


# --------------------------------------------------
# Dropdown values
# --------------------------------------------------

industries = (
    betas["Industry"]
    .tolist()
)

if DEFAULT_INDUSTRY not in industries:

    industries.insert(
        0,
        DEFAULT_INDUSTRY
    )


countries = sorted(
    set(yields)
    | set(taxes)
    | {"United States"}
)


# --------------------------------------------------
# Sidebar
# --------------------------------------------------

with st.sidebar:

    st.header(
        "Project settings"
    )

    industry = st.selectbox(
        "Industry",
        industries,
        index=industries.index(
            DEFAULT_INDUSTRY
        )
    )

    country = st.selectbox(
        "Target country",
        countries,
        index=countries.index(
            "United States"
        )
    )

    erp = (
        st.number_input(
            "Equity risk premium (%)",
            0.0,
            20.0,
            6.5,
            0.1
        )
        / 100
    )

    debt = (
        st.slider(
            "Target debt share (%)",
            0,
            95,
            30,
            1
        )
        / 100
    )


    # Automatic source data

    beta_auto_series = (
        betas.loc[
            betas["Industry"] == industry,
            "Unlevered Beta"
        ]
    )

    beta_auto = (
        float(
            beta_auto_series.iloc[0]
        )
        if len(beta_auto_series)
        else 1.23
    )

    us_tax_auto = taxes.get(
        "United States",
        0.256
    )

    foreign_tax_auto = taxes.get(
        country,
        us_tax_auto
    )

    y_us_auto = yields.get(
        "United States",
        0.04
    )

    y_foreign_auto = yields.get(
        country,
        y_us_auto
    )


    # Tax choice

    st.subheader(
        "Tax basis"
    )

    tax_choice = st.radio(
        "Use project tax rate from:",
        [
            "United States",
            country
        ],
        index=0
    )

    if country == "United States":
        tax_choice = "United States"


    # Manual overrides

    st.subheader(
        "Manual overrides"
    )

    ov_beta = st.toggle(
        "Override unlevered beta"
    )

    beta_manual = st.number_input(
        "Unlevered beta",
        0.0,
        5.0,
        beta_auto,
        0.01,
        disabled=not ov_beta
    )


    ov_us_tax = st.toggle(
        "Override U.S. tax rate"
    )

    us_tax_manual = (
        st.number_input(
            "U.S. corporate tax rate (%)",
            0.0,
            60.0,
            us_tax_auto * 100,
            0.1,
            disabled=not ov_us_tax
        )
        / 100
    )


    ov_f_tax = st.toggle(
        f"Override {country} tax rate"
    )

    f_tax_manual = (
        st.number_input(
            f"{country} corporate tax rate (%)",
            0.0,
            60.0,
            foreign_tax_auto * 100,
            0.1,
            disabled=not ov_f_tax
        )
        / 100
    )


    ov_spread = st.toggle(
        "Override USD BBB spread"
    )

    spread_manual = (
        st.number_input(
            "USD BBB spread (%)",
            0.0,
            20.0,
            bbb * 100,
            0.01,
            disabled=not ov_spread
        )
        / 100
    )


    ov_y_us = st.toggle(
        "Override U.S. 10Y yield"
    )

    y_us_manual = (
        st.number_input(
            "U.S. 10Y government yield (%)",
            -5.0,
            50.0,
            y_us_auto * 100,
            0.01,
            disabled=not ov_y_us
        )
        / 100
    )


    ov_y_f = st.toggle(
        f"Override {country} 10Y yield"
    )

    y_f_manual = (
        st.number_input(
            f"{country} 10Y government yield (%)",
            -5.0,
            50.0,
            y_foreign_auto * 100,
            0.01,
            disabled=not ov_y_f
        )
        / 100
    )


    ov_f_spread = st.toggle(
        f"Override {country} BBB spread"
    )

    f_spread_manual = (
        st.number_input(
            f"{country} BBB spread (%)",
            0.0,
            30.0,
            bbb * 100,
            0.01,
            disabled=not ov_f_spread
        )
        / 100
    )


# --------------------------------------------------
# Apply overrides
# --------------------------------------------------

beta_u = (
    beta_manual
    if ov_beta
    else beta_auto
)

us_tax = (
    us_tax_manual
    if ov_us_tax
    else us_tax_auto
)

foreign_tax = (
    f_tax_manual
    if ov_f_tax
    else foreign_tax_auto
)

tax = (
    us_tax
    if tax_choice == "United States"
    else foreign_tax
)

spread_us = (
    spread_manual
    if ov_spread
    else bbb
)

y_us = (
    y_us_manual
    if ov_y_us
    else y_us_auto
)

y_foreign = (
    y_f_manual
    if ov_y_f
    else y_foreign_auto
)

f_spread_override = (
    f_spread_manual
    if ov_f_spread
    else None
)


# --------------------------------------------------
# Calculate
# --------------------------------------------------

r = calc(
    beta_u,
    tax,
    erp,
    debt,
    y_us,
    y_foreign,
    spread_us,
    f_spread_override
)


# --------------------------------------------------
# Main results
# --------------------------------------------------

st.subheader(
    f"{industry} — {country}"
)

st.write(
    f"Unlevered beta **{beta_u:.3f}** · "
    f"Levered beta **{r['beta_l']:.3f}** · "
    f"ERP **{pct(erp)}** · "
    f"Debt **{pct(debt)}** · "
    f"Project tax **{pct(tax)}**"
)


c1, c2 = st.columns(2)


with c1:

    st.markdown(
        "### 🇺🇸 USD"
    )

    a, b = st.columns(2)

    a.metric(
        "Cost of equity",
        pct(r["ke_us"])
    )

    b.metric(
        "WACC",
        pct(r["wacc_us"])
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(r['kd_us_pre'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(r['kd_us_after'])}**"
    )


with c2:

    st.markdown(
        f"### 🌐 {country} currency"
    )

    a, b = st.columns(2)

    a.metric(
        "Cost of equity",
        pct(r["ke_foreign"])
    )

    b.metric(
        "WACC",
        pct(r["wacc_foreign"])
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(r['kd_foreign_pre'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(r['kd_foreign_after'])}**"
    )

    st.write(
        "BBB spread: "
        f"**{pct(r['spread_foreign'])}**"
    )


# --------------------------------------------------
# Formulas
# --------------------------------------------------

with st.expander(
    "Formulas / assumptions",
    expanded=True
):

    st.markdown(
        r"""
**Relever beta**

\[
\beta_L
=
\beta_U
\left[
1+(1-\tau)\frac{D}{E}
\right]
\]

**USD cost of equity**

\[
k_{e,USD}
=
y_{US}
+
\beta_L \times ERP
\]

**USD pre-tax cost of debt**

\[
k_{d,USD}
=
y_{US}
+
Spread_{BBB,USD}
\]

**Currency conversion used in class**

\[
1+k_{foreign}
=
(1+k_{USD})
\frac{1+y_{foreign}}
{1+y_{US}}
\]

When the foreign BBB spread override is OFF,
the app converts the **full USD pre-tax debt cost**
and then subtracts the foreign government yield
to obtain the implied foreign spread.

**WACC**

\[
WACC
=
(1-d)k_e
+
d\,k_d(1-\tau)
\]
"""
    )


# --------------------------------------------------
# All-industry comparison
# --------------------------------------------------

st.subheader(
    "All-industry comparison"
)

rows = []

for _, x in betas.iterrows():

    z = calc(
        float(
            x["Unlevered Beta"]
        ),
        tax,
        erp,
        debt,
        y_us,
        y_foreign,
        spread_us,
        f_spread_override
    )

    rows.append(
        {
            "Industry":
                x["Industry"],

            "Unlevered Beta":
                float(
                    x["Unlevered Beta"]
                ),

            "Levered Beta":
                z["beta_l"],

            "USD Cost of Equity":
                z["ke_us"],

            "USD WACC":
                z["wacc_us"],

            f"{country} Cost of Equity":
                z["ke_foreign"],

            f"{country} WACC":
                z["wacc_foreign"],
        }
    )


all_df = pd.DataFrame(
    rows
)

show_df = all_df.copy()

for col in [
    c
    for c in show_df.columns
    if (
        "Cost of Equity" in c
        or "WACC" in c
    )
]:

    show_df[col] = (
        show_df[col]
        .map(pct)
    )


st.dataframe(
    show_df,
    hide_index=True,
    use_container_width=True,
    height=400
)


st.download_button(
    "⬇️ Download all-industry results",
    all_df
        .to_csv(index=False)
        .encode("utf-8"),
    "international_cost_of_capital_results.csv",
    "text/csv"
)


# --------------------------------------------------
# Verification tests
# --------------------------------------------------

st.subheader(
    "Verification"
)


# 1. Equal yields test

equal_yield = calc(
    beta_u,
    tax,
    erp,
    debt,
    y_us,
    y_us,
    spread_us,
    None
)


# 2. Zero debt test

zero_debt = calc(
    beta_u,
    tax,
    erp,
    0,
    y_us,
    y_foreign,
    spread_us,
    None
)


# 3. Foreign spread override test

foreign_override_test = calc(
    beta_u,
    tax,
    erp,
    debt,
    y_us,
    y_foreign,
    spread_us,
    r["spread_foreign"] + 0.01
)


checks = pd.DataFrame(
    {
        "Check": [

            (
                "Equal government yields → "
                "equal USD/local results"
            ),

            (
                "Zero debt → "
                "WACC equals cost of equity"
            ),

            (
                "Foreign spread override → "
                "USD results unchanged"
            ),
        ],

        "Result": [

            (
                "PASS ✅"
                if abs(
                    equal_yield["wacc_us"]
                    -
                    equal_yield["wacc_foreign"]
                ) < 1e-10
                else "FAIL ❌"
            ),

            (
                "PASS ✅"
                if (
                    abs(
                        zero_debt["wacc_us"]
                        -
                        zero_debt["ke_us"]
                    ) < 1e-10
                    and
                    abs(
                        zero_debt[
                            "wacc_foreign"
                        ]
                        -
                        zero_debt[
                            "ke_foreign"
                        ]
                    ) < 1e-10
                )
                else "FAIL ❌"
            ),

            (
                "PASS ✅"
                if abs(
                    foreign_override_test[
                        "wacc_us"
                    ]
                    -
                    r["wacc_us"]
                ) < 1e-10
                else "FAIL ❌"
            ),
        ]
    }
)


st.dataframe(
    checks,
    hide_index=True,
    use_container_width=True
)


# --------------------------------------------------
# Sources
# --------------------------------------------------

st.subheader(
    "Sources"
)

st.markdown(
    f"""
- **Damodaran industry beta:** {BETAS_URL}
- **Damodaran Baa2/BBB spread:** {RATINGS_URL}
- **OECD corporate tax rates:** {OECD_PAGE}
- **Trading Economics 10-year government yields:** {TE_URL}
- **Last app refresh:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
"""
)
