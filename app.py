import io
import re
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide",
)


# ============================================================
# Source URLs
# ============================================================

BETAS_XLS_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
BETAS_HTML_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/Betas.html"

RATINGS_URL = (
    "https://pages.stern.nyu.edu/adamodar/"
    "New_Home_Page/datafile/ratings.html"
)

OECD_PAGE_URL = (
    "https://www.oecd.org/en/publications/"
    "corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_"
    "440f9286.html"
)

OECD_XLSX_URL = "https://stat.link/0qkxo1"

TRADING_ECONOMICS_URL = "https://tradingeconomics.com/bonds"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_COUNTRY = "United States"
DEFAULT_ERP = 0.065
DEFAULT_DEBT_SHARE = 0.30

FALLBACK_BETA = 1.23
FALLBACK_US_TAX = 0.2563
FALLBACK_BBB_SPREAD = 0.0111
FALLBACK_US_10Y = 0.04

COUNTRY_ALIASES = {
    "USA": "United States",
    "US": "United States",
    "U.S.": "United States",
    "United States of America": "United States",
    "Korea": "South Korea",
    "Korea, Rep.": "South Korea",
    "Republic of Korea": "South Korea",
    "Türkiye": "Turkey",
    "Czech Republic": "Czechia",
    "Russian Federation": "Russia",
    "Viet Nam": "Vietnam",
    "China (People's Republic of)": "China",
}


# ============================================================
# General helpers
# ============================================================

def normalize_country(value):
    value = re.sub(r"\s+", " ", str(value)).strip()
    return COUNTRY_ALIASES.get(value, value)


def parse_rate(value):
    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        value = float(value)
        return value / 100.0 if abs(value) > 1 else value

    text = str(value).replace(",", "").strip()

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    number = float(match.group())

    if "%" in text or abs(number) > 1:
        number /= 100.0

    return number


def pct(value):
    return f"{100 * value:.2f}%"


def request_bytes(url, timeout=30):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )
    response.raise_for_status()
    return response.content


def request_text(url, timeout=30):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )
    response.raise_for_status()
    return response.text


# ============================================================
# Damodaran industry beta
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_betas_from_xls():

    content = request_bytes(
        BETAS_XLS_URL
    )

    raw = pd.read_excel(
        io.BytesIO(content),
        sheet_name="Industry Averages",
        header=None,
        engine="xlrd",
    )

    header_candidates = raw.index[
        raw.iloc[:, 0]
        .astype(str)
        .str.strip()
        .eq("Industry Name")
    ].tolist()

    if not header_candidates:
        raise ValueError(
            "Could not find 'Industry Name' "
            "in Industry Averages sheet."
        )

    header_row = header_candidates[0]

    header = [
        re.sub(
            r"\s+",
            " ",
            str(x)
        ).strip()
        for x in raw.iloc[header_row].tolist()
    ]

    data = raw.iloc[
        header_row + 1:
    ].copy()

    data.columns = header

    beta_col = next(
        (
            col
            for col in data.columns
            if col.lower() == "unlevered beta"
        ),
        None
    )

    if beta_col is None:
        raise ValueError(
            "Unlevered Beta column not found."
        )

    out = data[
        [
            "Industry Name",
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

    out = out.dropna(
        subset=["Unlevered Beta"]
    )

    out = out[
        out["Industry"].ne("")
    ]

    out = out[
        out["Industry"]
        .str.lower()
        .ne("nan")
    ]

    out = out.drop_duplicates(
        "Industry"
    )

    if len(out) < 20:
        raise ValueError(
            "Too few industry rows were parsed."
        )

    return (
        out
        .sort_values("Industry")
        .reset_index(drop=True)
    )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_betas_from_html():

    html = request_text(
        BETAS_HTML_URL
    )

    tables = pd.read_html(
        io.StringIO(html),
        flavor="lxml"
    )

    for table in tables:

        table.columns = [
            re.sub(
                r"\s+",
                " ",
                str(c)
            ).strip()
            for c in table.columns
        ]

        industry_col = next(
            (
                c
                for c in table.columns
                if c.lower() == "industry name"
            ),
            None
        )

        beta_col = next(
            (
                c
                for c in table.columns
                if c.lower() == "unlevered beta"
            ),
            None
        )

        if industry_col and beta_col:

            out = table[
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

            if len(out) >= 20:

                return (
                    out
                    .sort_values("Industry")
                    .reset_index(drop=True)
                )

    raise ValueError(
        "Could not parse Damodaran beta table."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_betas():

    try:

        return (
            fetch_betas_from_xls(),
            "Damodaran betas.xls"
        )

    except Exception as xls_error:

        try:

            return (
                fetch_betas_from_html(),
                "Damodaran HTML fallback"
            )

        except Exception as html_error:

            raise ValueError(
                f"XLS error: {xls_error}; "
                f"HTML error: {html_error}"
            )


# ============================================================
# Damodaran BBB spread
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_bbb_spread():

    html = request_text(
        RATINGS_URL
    )

    tables = pd.read_html(
        io.StringIO(html),
        flavor="lxml"
    )

    for table in tables:

        for _, row in table.iterrows():

            values = [
                str(v).strip()
                for v in row.tolist()
            ]

            for idx, value in enumerate(
                values
            ):

                if "Baa2/BBB" in value:

                    for candidate in values[
                        idx + 1:
                    ]:

                        rate = parse_rate(
                            candidate
                        )

                        if (
                            rate is not None
                            and 0 < rate < 0.10
                        ):
                            return rate

    match = re.search(
        r"Baa2/BBB.{0,300}?"
        r"(\d+(?:\.\d+)?)%",
        html,
        flags=re.IGNORECASE
    )

    if match:
        return (
            float(match.group(1))
            / 100.0
        )

    raise ValueError(
        "Could not locate Baa2/BBB spread."
    )


# ============================================================
# OECD corporate tax rates
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_tax_rates():

    content = request_bytes(
        OECD_XLSX_URL
    )

    sheets = pd.read_excel(
        io.BytesIO(content),
        sheet_name=None,
        header=None,
        engine="openpyxl",
    )

    rates = {}

    skip_words = (
        "source",
        "note",
        "figure",
        "average",
        "statutory",
        "corporate",
        "jurisdiction",
        "year",
        "oecd",
    )

    for sheet in sheets.values():

        for _, row in sheet.iterrows():

            cells = [
                x
                for x in row.tolist()
                if not pd.isna(x)
            ]

            if not cells:
                continue

            text_cells = [
                str(x).strip()
                for x in cells
                if isinstance(x, str)
            ]

            numeric_cells = []

            for x in cells:

                if isinstance(
                    x,
                    (int, float)
                ):

                    value = float(x)

                    if (
                        0
                        <= value
                        <= 100
                    ):
                        numeric_cells.append(
                            value
                        )

            if (
                not text_cells
                or not numeric_cells
            ):
                continue

            country = text_cells[0]

            country_lower = (
                country.lower()
            )

            if any(
                word in country_lower
                for word in skip_words
            ):
                continue

            if (
                len(country) < 2
                or len(country) > 70
            ):
                continue

            raw_rate = numeric_cells[-1]

            rate = (
                raw_rate
                if raw_rate <= 1
                else raw_rate / 100.0
            )

            if (
                0
                <= rate
                <= 0.60
            ):

                rates[
                    normalize_country(
                        country
                    )
                ] = rate

    if len(rates) < 20:

        raise ValueError(
            f"Only {len(rates)} OECD "
            "tax rates were parsed."
        )

    return rates


# ============================================================
# Trading Economics 10Y yields
# ============================================================

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_government_yields():

    html = request_text(
        TRADING_ECONOMICS_URL
    )

    tables = pd.read_html(
        io.StringIO(html),
        flavor="lxml"
    )

    yields = {}

    for table in tables:

        if (
            table.empty
            or len(table.columns) < 2
        ):
            continue

        if isinstance(
            table.columns,
            pd.MultiIndex
        ):

            table.columns = [
                " ".join(
                    str(x).strip()
                    for x in col
                    if str(x) != "nan"
                ).strip()
                for col in table.columns
            ]

        else:

            table.columns = [
                str(c).strip()
                for c in table.columns
            ]

        country_col = next(
            (
                c
                for c in table.columns
                if "country" in c.lower()
            ),
            table.columns[0]
        )

        yield_col = next(
            (
                c
                for c in table.columns
                if "yield" in c.lower()
            ),
            None
        )

        if yield_col is None:

            yield_col = next(
                (
                    c
                    for c in table.columns
                    if c.lower() == "last"
                ),
                None
            )

        if (
            yield_col is None
            and len(table.columns) >= 2
        ):
            yield_col = table.columns[1]

        if yield_col is None:
            continue

        for _, row in table.iterrows():

            country = normalize_country(
                row.get(
                    country_col,
                    ""
                )
            )

            rate = parse_rate(
                row.get(
                    yield_col
                )
            )

            if (
                country
                and country.lower()
                not in {
                    "nan",
                    "country"
                }
                and rate is not None
                and -0.05 < rate < 0.50
            ):

                yields[
                    country
                ] = rate

    if "United States" not in yields:

        raise ValueError(
            "United States 10Y yield "
            "was not found."
        )

    return yields


# ============================================================
# Finance calculations
# ============================================================

def relever_beta(
    beta_u,
    tax_rate,
    debt_share
):

    if debt_share <= 0:
        return beta_u

    debt_to_equity = (
        debt_share
        / (1 - debt_share)
    )

    return (
        beta_u
        * (
            1
            + (1 - tax_rate)
            * debt_to_equity
        )
    )


def calculate_costs(
    beta_u,
    tax_rate,
    erp,
    debt_share,
    us_yield,
    foreign_yield,
    usd_bbb_spread,
    foreign_spread_override=None,
):

    beta_l = relever_beta(
        beta_u,
        tax_rate,
        debt_share
    )

    ke_usd = (
        us_yield
        + beta_l * erp
    )

    kd_usd_pre = (
        us_yield
        + usd_bbb_spread
    )

    kd_usd_after = (
        kd_usd_pre
        * (1 - tax_rate)
    )

    wacc_usd = (
        (1 - debt_share)
        * ke_usd
        + debt_share
        * kd_usd_after
    )

    currency_factor = (
        (1 + foreign_yield)
        / (1 + us_yield)
    )

    ke_foreign = (
        (1 + ke_usd)
        * currency_factor
        - 1
    )

    if foreign_spread_override is None:

        kd_foreign_pre = (
            (1 + kd_usd_pre)
            * currency_factor
            - 1
        )

        foreign_bbb_spread = (
            kd_foreign_pre
            - foreign_yield
        )

    else:

        foreign_bbb_spread = (
            foreign_spread_override
        )

        kd_foreign_pre = (
            foreign_yield
            + foreign_bbb_spread
        )

    kd_foreign_after = (
        kd_foreign_pre
        * (1 - tax_rate)
    )

    wacc_foreign = (
        (1 - debt_share)
        * ke_foreign
        + debt_share
        * kd_foreign_after
    )

    return {

        "beta_u":
            beta_u,

        "beta_l":
            beta_l,

        "tax_rate":
            tax_rate,

        "erp":
            erp,

        "debt_share":
            debt_share,

        "us_yield":
            us_yield,

        "foreign_yield":
            foreign_yield,

        "usd_bbb_spread":
            usd_bbb_spread,

        "foreign_bbb_spread":
            foreign_bbb_spread,

        "ke_usd":
            ke_usd,

        "kd_usd_pre":
            kd_usd_pre,

        "kd_usd_after":
            kd_usd_after,

        "wacc_usd":
            wacc_usd,

        "ke_foreign":
            ke_foreign,

        "kd_foreign_pre":
            kd_foreign_pre,

        "kd_foreign_after":
            kd_foreign_after,

        "wacc_foreign":
            wacc_foreign,
    }


# ============================================================
# Header
# ============================================================

st.title(
    "🌍 International Cost of Capital"
)

st.caption(
    "Compare a project's cost of equity "
    "and WACC in USD and in a selected "
    "country's currency."
)


if st.button(
    "🔄 Refresh source data"
):

    st.cache_data.clear()

    st.rerun()


# ============================================================
# Fetch data
# ============================================================

warnings = []


try:

    betas, beta_source_name = (
        fetch_betas()
    )

except Exception as exc:

    betas = pd.DataFrame(
        {
            "Industry": [
                DEFAULT_INDUSTRY
            ],
            "Unlevered Beta": [
                FALLBACK_BETA
            ],
        }
    )

    beta_source_name = (
        "Fallback value"
    )

    warnings.append(
        f"Damodaran beta fetch failed: {exc}"
    )


try:

    bbb_spread = (
        fetch_bbb_spread()
    )

except Exception as exc:

    bbb_spread = (
        FALLBACK_BBB_SPREAD
    )

    warnings.append(
        f"Damodaran BBB spread fetch failed: {exc}"
    )


try:

    tax_rates = (
        fetch_tax_rates()
    )

except Exception as exc:

    tax_rates = {
        "United States":
            FALLBACK_US_TAX,
        "Colombia":
            0.35,
    }

    warnings.append(
        f"OECD tax-rate fetch failed: {exc}"
    )


try:

    government_yields = (
        fetch_government_yields()
    )

except Exception as exc:

    government_yields = {
        "United States":
            FALLBACK_US_10Y
    }

    warnings.append(
        f"Trading Economics yield fetch failed: {exc}"
    )


for warning in warnings:

    st.warning(
        warning
        + " — manual override remains available."
    )


# ============================================================
# Sidebar
# ============================================================

industries = (
    betas["Industry"]
    .dropna()
    .astype(str)
    .tolist()
)


if DEFAULT_INDUSTRY not in industries:

    industries = (
        [DEFAULT_INDUSTRY]
        + industries
    )


countries = sorted(
    set(tax_rates.keys())
    | set(government_yields.keys())
    | {DEFAULT_COUNTRY}
)


with st.sidebar:

    st.header(
        "Project settings"
    )

    industry = st.selectbox(
        "Industry",
        industries,
        index=(
            industries.index(
                DEFAULT_INDUSTRY
            )
            if DEFAULT_INDUSTRY
            in industries
            else 0
        ),
    )

    country = st.selectbox(
        "Target country",
        countries,
        index=(
            countries.index(
                DEFAULT_COUNTRY
            )
            if DEFAULT_COUNTRY
            in countries
            else 0
        ),
    )

    erp = (
        st.number_input(
            "Equity risk premium (%)",
            min_value=0.0,
            max_value=20.0,
            value=6.5,
            step=0.1,
        )
        / 100.0
    )

    debt_share = (
        st.slider(
            "Target debt share (%)",
            min_value=0,
            max_value=95,
            value=30,
            step=1,
        )
        / 100.0
    )


    beta_match = betas.loc[
        betas["Industry"]
        == industry,
        "Unlevered Beta",
    ]

    beta_auto = (
        float(
            beta_match.iloc[0]
        )
        if len(beta_match)
        else FALLBACK_BETA
    )


    us_tax_auto = (
        tax_rates.get(
            "United States",
            FALLBACK_US_TAX
        )
    )


    foreign_tax_found = (
        country in tax_rates
    )

    foreign_tax_auto = (
        tax_rates.get(
            country,
            us_tax_auto
        )
    )


    us_yield_auto = (
        government_yields.get(
            "United States",
            FALLBACK_US_10Y
        )
    )


    foreign_yield_found = (
        country
        in government_yields
    )

    foreign_yield_auto = (
        government_yields.get(
            country,
            us_yield_auto
        )
    )


    st.subheader(
        "Tax basis"
    )


    tax_options = (
        ["United States"]
        if country
        == "United States"
        else [
            "United States",
            country
        ]
    )


    tax_choice = st.radio(
        "Use project tax rate from:",
        tax_options,
        index=0,
    )


    st.subheader(
        "Manual overrides"
    )


    override_beta = st.toggle(
        "Override unlevered beta",
        value=False
    )

    beta_manual = st.number_input(
        "Unlevered beta",
        min_value=0.0,
        max_value=5.0,
        value=float(beta_auto),
        step=0.01,
        disabled=not override_beta,
    )


    override_us_tax = st.toggle(
        "Override U.S. tax rate",
        value=False
    )

    us_tax_manual = (
        st.number_input(
            "U.S. corporate tax rate (%)",
            min_value=0.0,
            max_value=60.0,
            value=float(
                us_tax_auto * 100
            ),
            step=0.1,
            disabled=not override_us_tax,
        )
        / 100.0
    )


    override_foreign_tax = st.toggle(
        f"Override {country} tax rate",
        value=False,
    )

    foreign_tax_manual = (
        st.number_input(
            f"{country} corporate tax rate (%)",
            min_value=0.0,
            max_value=60.0,
            value=float(
                foreign_tax_auto * 100
            ),
            step=0.1,
            disabled=not override_foreign_tax,
        )
        / 100.0
    )


    override_us_spread = st.toggle(
        "Override USD BBB spread",
        value=False
    )

    usd_spread_manual = (
        st.number_input(
            "USD BBB spread (%)",
            min_value=0.0,
            max_value=20.0,
            value=float(
                bbb_spread * 100
            ),
            step=0.01,
            disabled=not override_us_spread,
        )
        / 100.0
    )


    override_us_yield = st.toggle(
        "Override U.S. 10Y yield",
        value=False
    )

    us_yield_manual = (
        st.number_input(
            "U.S. 10Y government yield (%)",
            min_value=-5.0,
            max_value=50.0,
            value=float(
                us_yield_auto * 100
            ),
            step=0.01,
            disabled=not override_us_yield,
        )
        / 100.0
    )


    override_foreign_yield = st.toggle(
        f"Override {country} 10Y yield",
        value=False,
    )

    foreign_yield_manual = (
        st.number_input(
            f"{country} 10Y government yield (%)",
            min_value=-5.0,
            max_value=50.0,
            value=float(
                foreign_yield_auto * 100
            ),
            step=0.01,
            disabled=not override_foreign_yield,
        )
        / 100.0
    )


    override_foreign_spread = st.toggle(
        f"Override {country} BBB spread",
        value=False,
    )

    foreign_spread_manual = (
        st.number_input(
            f"{country} BBB spread (%)",
            min_value=0.0,
            max_value=30.0,
            value=float(
                bbb_spread * 100
            ),
            step=0.01,
            disabled=not override_foreign_spread,
        )
        / 100.0
    )


# ============================================================
# Apply overrides
# ============================================================

beta_u = (
    beta_manual
    if override_beta
    else beta_auto
)


us_tax = (
    us_tax_manual
    if override_us_tax
    else us_tax_auto
)


foreign_tax = (
    foreign_tax_manual
    if override_foreign_tax
    else foreign_tax_auto
)


tax_rate = (
    us_tax
    if tax_choice == "United States"
    else foreign_tax
)


usd_bbb_spread = (
    usd_spread_manual
    if override_us_spread
    else bbb_spread
)


us_yield = (
    us_yield_manual
    if override_us_yield
    else us_yield_auto
)


foreign_yield = (
    foreign_yield_manual
    if override_foreign_yield
    else foreign_yield_auto
)


foreign_spread_override = (
    foreign_spread_manual
    if override_foreign_spread
    else None
)


if (
    country != "United States"
    and not foreign_tax_found
    and not override_foreign_tax
):

    st.info(
        f"OECD tax rate for {country} "
        "was not parsed. "
        "Use manual override."
    )


if (
    country != "United States"
    and not foreign_yield_found
    and not override_foreign_yield
):

    st.info(
        f"Trading Economics yield for {country} "
        "was not parsed. "
        "Use manual override."
    )


# ============================================================
# Main calculation
# ============================================================

result = calculate_costs(
    beta_u=beta_u,
    tax_rate=tax_rate,
    erp=erp,
    debt_share=debt_share,
    us_yield=us_yield,
    foreign_yield=foreign_yield,
    usd_bbb_spread=usd_bbb_spread,
    foreign_spread_override=foreign_spread_override,
)


# ============================================================
# Results
# ============================================================

st.subheader(
    f"{industry} — {country}"
)


st.write(
    f"Unlevered beta **{result['beta_u']:.3f}** · "
    f"Levered beta **{result['beta_l']:.3f}** · "
    f"ERP **{pct(result['erp'])}** · "
    f"Debt **{pct(result['debt_share'])}** · "
    f"Project tax **{pct(result['tax_rate'])}**"
)


left, right = st.columns(2)


with left:

    st.markdown(
        "### 🇺🇸 USD"
    )

    a, b = st.columns(2)

    a.metric(
        "Cost of equity",
        pct(
            result["ke_usd"]
        )
    )

    b.metric(
        "WACC",
        pct(
            result["wacc_usd"]
        )
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(result['kd_usd_pre'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(result['kd_usd_after'])}**"
    )

    st.write(
        "BBB spread: "
        f"**{pct(result['usd_bbb_spread'])}**"
    )


with right:

    st.markdown(
        f"### 🌐 {country} currency"
    )

    a, b = st.columns(2)

    a.metric(
        "Cost of equity",
        pct(
            result["ke_foreign"]
        )
    )

    b.metric(
        "WACC",
        pct(
            result["wacc_foreign"]
        )
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(result['kd_foreign_pre'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(result['kd_foreign_after'])}**"
    )

    st.write(
        "BBB spread: "
        f"**{pct(result['foreign_bbb_spread'])}**"
    )


# ============================================================
# Formula display
# ============================================================

with st.expander(
    "Formulas / assumptions",
    expanded=True
):

    st.markdown(
        "**Relever beta**"
    )

    st.latex(
        r"\beta_L="
        r"\beta_U"
        r"\left["
        r"1+(1-\tau)"
        r"\frac{D}{E}"
        r"\right]"
    )


    st.markdown(
        "**USD cost of equity**"
    )

    st.latex(
        r"k_{e,USD}"
        r"="
        r"y_{US}"
        r"+"
        r"\beta_L"
        r"\times ERP"
    )


    st.markdown(
        "**USD pre-tax cost of debt**"
    )

    st.latex(
        r"k_{d,USD}"
        r"="
        r"y_{US}"
        r"+"
        r"Spread_{BBB,USD}"
    )


    st.markdown(
        "**Currency conversion used in class**"
    )

    st.latex(
        r"1+k_{foreign}"
        r"="
        r"(1+k_{USD})"
        r"\frac{1+y_{foreign}}"
        r"{1+y_{US}}"
    )


    st.markdown(
        "When the foreign BBB spread override "
        "is **OFF**, the app converts the "
        "**full USD pre-tax borrowing cost** "
        "into the target currency and then "
        "subtracts the foreign government yield."
    )


    st.markdown(
        "**WACC**"
    )

    st.latex(
        r"WACC="
        r"(1-d)k_e"
        r"+"
        r"d\,k_d(1-\tau)"
    )


# ============================================================
# Calculation detail
# ============================================================

st.subheader(
    "Calculation detail"
)


calculation_detail = pd.DataFrame(
    {
        "Input / output": [

            "Unlevered beta",

            "Levered beta",

            "Equity risk premium",

            "Debt share",

            "Project tax rate",

            "U.S. 10Y government yield",

            f"{country} 10Y government yield",

            "USD BBB spread",

            f"{country} BBB spread",

            "USD cost of equity",

            f"{country} cost of equity",

            "USD pre-tax cost of debt",

            f"{country} pre-tax cost of debt",

            "USD WACC",

            f"{country} WACC",
        ],

        "Value": [

            f"{result['beta_u']:.3f}",

            f"{result['beta_l']:.3f}",

            pct(result["erp"]),

            pct(result["debt_share"]),

            pct(result["tax_rate"]),

            pct(result["us_yield"]),

            pct(result["foreign_yield"]),

            pct(result["usd_bbb_spread"]),

            pct(result["foreign_bbb_spread"]),

            pct(result["ke_usd"]),

            pct(result["ke_foreign"]),

            pct(result["kd_usd_pre"]),

            pct(result["kd_foreign_pre"]),

            pct(result["wacc_usd"]),

            pct(result["wacc_foreign"]),
        ],
    }
)


st.dataframe(
    calculation_detail,
    hide_index=True,
    use_container_width=True,
)


# ============================================================
# All-industry comparison
# ============================================================

st.subheader(
    "All-industry comparison"
)


industry_rows = []


for _, row in betas.iterrows():

    try:

        industry_result = calculate_costs(
            beta_u=float(
                row["Unlevered Beta"]
            ),
            tax_rate=tax_rate,
            erp=erp,
            debt_share=debt_share,
            us_yield=us_yield,
            foreign_yield=foreign_yield,
            usd_bbb_spread=usd_bbb_spread,
            foreign_spread_override=foreign_spread_override,
        )

        industry_rows.append(
            {
                "Industry":
                    row["Industry"],

                "Unlevered Beta":
                    industry_result["beta_u"],

                "Levered Beta":
                    industry_result["beta_l"],

                "USD Cost of Equity":
                    industry_result["ke_usd"],

                "USD WACC":
                    industry_result["wacc_usd"],

                f"{country} Cost of Equity":
                    industry_result["ke_foreign"],

                f"{country} WACC":
                    industry_result["wacc_foreign"],
            }
        )

    except Exception:

        pass


all_industries = pd.DataFrame(
    industry_rows
)


all_industries_display = (
    all_industries.copy()
)


for column in all_industries_display.columns:

    if (
        "Cost of Equity" in column
        or "WACC" in column
    ):

        all_industries_display[
            column
        ] = (
            all_industries_display[
                column
            ].map(pct)
        )


st.dataframe(
    all_industries_display,
    hide_index=True,
    use_container_width=True,
    height=420,
)


selected_download = pd.DataFrame(
    [
        {
            "Industry":
                industry,

            "Target Country":
                country,

            **result,
        }
    ]
).to_csv(
    index=False
).encode(
    "utf-8"
)


all_download = (
    all_industries
    .to_csv(index=False)
    .encode("utf-8")
)


c1, c2 = st.columns(2)


c1.download_button(
    "⬇️ Download selected result",
    data=selected_download,
    file_name="selected_cost_of_capital.csv",
    mime="text/csv",
    use_container_width=True,
)


c2.download_button(
    "⬇️ Download all industries",
    data=all_download,
    file_name="all_industries_cost_of_capital.csv",
    mime="text/csv",
    use_container_width=True,
)


# ============================================================
# Verification checks
# ============================================================

st.subheader(
    "Verification checks"
)


check_equal_yields = calculate_costs(
    beta_u=beta_u,
    tax_rate=tax_rate,
    erp=erp,
    debt_share=debt_share,
    us_yield=us_yield,
    foreign_yield=us_yield,
    usd_bbb_spread=usd_bbb_spread,
    foreign_spread_override=None,
)


pass_equal_yields = (
    abs(
        check_equal_yields["ke_usd"]
        - check_equal_yields["ke_foreign"]
    )
    < 1e-12

    and

    abs(
        check_equal_yields["wacc_usd"]
        - check_equal_yields["wacc_foreign"]
    )
    < 1e-12
)


check_zero_debt = calculate_costs(
    beta_u=beta_u,
    tax_rate=tax_rate,
    erp=erp,
    debt_share=0.0,
    us_yield=us_yield,
    foreign_yield=foreign_yield,
    usd_bbb_spread=usd_bbb_spread,
    foreign_spread_override=None,
)


pass_zero_debt = (
    abs(
        check_zero_debt["wacc_usd"]
        - check_zero_debt["ke_usd"]
    )
    < 1e-12

    and

    abs(
        check_zero_debt["wacc_foreign"]
        - check_zero_debt["ke_foreign"]
    )
    < 1e-12
)


check_foreign_override = calculate_costs(
    beta_u=beta_u,
    tax_rate=tax_rate,
    erp=erp,
    debt_share=debt_share,
    us_yield=us_yield,
    foreign_yield=foreign_yield,
    usd_bbb_spread=usd_bbb_spread,
    foreign_spread_override=(
        result["foreign_bbb_spread"]
        + 0.01
    ),
)


pass_foreign_override = (
    abs(
        check_foreign_override["ke_usd"]
        - result["ke_usd"]
    )
    < 1e-12

    and

    abs(
        check_foreign_override["wacc_usd"]
        - result["wacc_usd"]
    )
    < 1e-12
)


verification_table = pd.DataFrame(
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

        "Status": [

            (
                "PASS ✅"
                if pass_equal_yields
                else "FAIL ❌"
            ),

            (
                "PASS ✅"
                if pass_zero_debt
                else "FAIL ❌"
            ),

            (
                "PASS ✅"
                if pass_foreign_override
                else "FAIL ❌"
            ),
        ],
    }
)


st.dataframe(
    verification_table,
    hide_index=True,
    use_container_width=True,
)


# ============================================================
# Sources
# ============================================================

st.subheader(
    "Sources and dates"
)


source_table = pd.DataFrame(
    {
        "Data": [

            "U.S. industry unlevered beta",

            "BBB USD borrowing spread",

            "Corporate tax rate",

            "10-year government yield",
        ],

        "Source": [

            beta_source_name,

            "Damodaran ratings table",

            "OECD Corporate Tax Statistics 2024",

            "Trading Economics",
        ],

        "Date / refresh": [

            "Damodaran January 2026 data",

            "Damodaran January 2026 data",

            "2024 statutory rate data",

            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
        ],

        "URL": [

            BETAS_XLS_URL,

            RATINGS_URL,

            OECD_PAGE_URL,

            TRADING_ECONOMICS_URL,
        ],
    }
)


st.dataframe(
    source_table,
    hide_index=True,
    use_container_width=True,
)


st.caption(
    "Coursework app using the simplified "
    "formulas discussed in class. "
    "Manual overrides are available "
    "if an external source cannot be fetched."
)
