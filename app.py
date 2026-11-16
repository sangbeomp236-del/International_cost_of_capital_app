import io
import os
import re
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import pycountry
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="International Cost of Capital",
    page_icon="🌍",
    layout="wide",
)

# ============================================================
# Professor-provided source URLs
# ============================================================

BETAS_XLS_URL = (
    "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
)

OECD_PAGE_URL = (
    "https://www.oecd.org/en/publications/"
    "corporate-tax-statistics-2024_9c27d6e8-en/full-report/"
    "statutory-corporate-income-tax-rates_440f9286.html"
    "#chapter-d1e2342-08e74a33fb"
)

RATINGS_URL = (
    "https://pages.stern.nyu.edu/adamodar/"
    "New_Home_Page/datafile/ratings.html"
)

TE_BONDS_URL = "https://tradingeconomics.com/bonds"

# Official OECD Statlink underlying the professor-provided OECD page.
OECD_STATLINK_URL = "https://stat.link/0qkxo1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_COUNTRY = "United States"

# Emergency fallbacks only.
FALLBACK_BETA = 1.225
FALLBACK_US_TAX = 0.2563
FALLBACK_BBB = 0.0111
FALLBACK_US_10Y = 0.04


# ============================================================
# Country-name helpers
# ============================================================

ALIASES = {
    "United States of America": "United States",
    "USA": "United States",
    "US": "United States",
    "U.S.": "United States",

    "Korea, Republic of": "South Korea",
    "Republic of Korea": "South Korea",
    "Korea": "South Korea",
    "Korea, Rep.": "South Korea",

    "United Kingdom of Great Britain and Northern Ireland":
        "United Kingdom",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",

    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Viet Nam": "Vietnam",
    "Russian Federation": "Russia",
    "China (People's Republic of)": "China",
    "Hong Kong, China": "Hong Kong",
    "Taiwan, Province of China": "Taiwan",
    "Slovak Republic": "Slovakia",
}


def now_utc():
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def normalize_country(x):
    x = re.sub(
        r"\s+",
        " ",
        str(x)
    ).strip()

    if x in ALIASES:
        return ALIASES[x]

    if (
        len(x) == 3
        and x.isalpha()
        and x.upper() == x
    ):
        country = pycountry.countries.get(
            alpha_3=x
        )

        if country:
            return ALIASES.get(
                country.name,
                country.name
            )

    return ALIASES.get(
        x,
        x
    )


def parse_rate(x):
    if x is None or pd.isna(x):
        return None

    if isinstance(
        x,
        (int, float)
    ):
        x = float(x)

        return (
            x / 100
            if abs(x) > 1
            else x
        )

    text = (
        str(x)
        .replace(",", "")
        .strip()
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    value = float(
        match.group()
    )

    if (
        "%" in text
        or abs(value) > 1
    ):
        value /= 100

    return value


def pct(x):
    return f"{x * 100:.2f}%"


def get_text(
    url,
    timeout=30
):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    return response.text


def get_bytes(
    url,
    timeout=30
):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    return response.content


# ============================================================
# 1. Damodaran betas.xls
# ============================================================

def parse_beta_xls(content):

    book = pd.ExcelFile(
        io.BytesIO(content),
        engine="xlrd",
    )

    for sheet in book.sheet_names:

        raw = pd.read_excel(
            io.BytesIO(content),
            sheet_name=sheet,
            header=None,
            engine="xlrd",
        )

        for i in range(
            min(60, len(raw))
        ):

            cells = [
                str(v).strip()
                for v in raw.iloc[i].tolist()
            ]

            lower = [
                v.lower()
                for v in cells
            ]

            industry_col = next(
                (
                    j
                    for j, v
                    in enumerate(lower)
                    if v in {
                        "industry",
                        "industry name"
                    }
                ),
                None,
            )

            beta_col = next(
                (
                    j
                    for j, v
                    in enumerate(lower)
                    if (
                        "unlevered beta" in v
                        and "cash" not in v
                    )
                ),
                None,
            )

            if (
                industry_col is None
                or beta_col is None
            ):
                continue

            out = raw.iloc[
                i + 1:,
                [
                    industry_col,
                    beta_col
                ],
            ].copy()

            out.columns = [
                "Industry",
                "Unlevered Beta",
            ]

            out["Industry"] = (
                out["Industry"]
                .astype(str)
                .str.strip()
            )

            out["Unlevered Beta"] = (
                pd.to_numeric(
                    out["Unlevered Beta"],
                    errors="coerce",
                )
            )

            out = out.dropna(
                subset=[
                    "Unlevered Beta"
                ]
            )

            out = out[
                (
                    out["Industry"] != ""
                )
                &
                (
                    out["Industry"]
                    .str.lower()
                    != "nan"
                )
            ]

            out = out.drop_duplicates(
                "Industry"
            )

            if len(out) >= 20:

                return (
                    out
                    .sort_values(
                        "Industry"
                    )
                    .reset_index(
                        drop=True
                    )
                )

    raise ValueError(
        "Industry Name / Unlevered Beta "
        "not found in betas.xls."
    )


@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def fetch_betas():

    try:

        content = get_bytes(
            BETAS_XLS_URL
        )

        data = parse_beta_xls(
            content
        )

        return (
            data,
            "Damodaran betas.xls (live web file)",
            now_utc(),
        )

    except Exception as web_error:

        if os.path.exists(
            "betas.xls"
        ):

            with open(
                "betas.xls",
                "rb"
            ) as file:

                content = file.read()

            data = parse_beta_xls(
                content
            )

            return (
                data,
                "Damodaran betas.xls (local backup)",
                f"Live fetch failed: {web_error}",
            )

        raise


# ============================================================
# 2. Damodaran BBB borrowing spread
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def fetch_bbb():

    html = get_text(
        RATINGS_URL
    )

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    for row in soup.find_all(
        "tr"
    ):

        cells = [
            cell.get_text(
                " ",
                strip=True,
            )
            for cell
            in row.find_all(
                ["td", "th"]
            )
        ]

        if not any(
            "Baa2/BBB" in cell
            for cell in cells
        ):
            continue

        rating_index = next(
            i
            for i, cell
            in enumerate(cells)
            if "Baa2/BBB" in cell
        )

        for candidate in cells[
            rating_index + 1:
        ]:

            if "%" not in candidate:
                continue

            value = parse_rate(
                candidate
            )

            if (
                value is not None
                and 0 < value < 0.10
            ):

                page_text = (
                    soup.get_text(
                        " ",
                        strip=True,
                    )
                )

                match = re.search(
                    r"Date of Analysis:"
                    r"\s*Data used is as of"
                    r"\s*([A-Za-z]+\s+\d{4})",
                    page_text,
                    flags=re.I,
                )

                date_text = (
                    match.group(1)
                    if match
                    else f"Fetched {now_utc()}"
                )

                return (
                    value,
                    date_text
                )

    raise ValueError(
        "Baa2/BBB spread not found."
    )


# ============================================================
# 3. OECD Corporate Tax Statistics 2024
# ============================================================

def parse_oecd_xlsx(content):

    sheets = pd.read_excel(
        io.BytesIO(content),
        sheet_name=None,
        header=None,
        engine="openpyxl",
    )

    rates = {}

    skip = {
        "source",
        "note",
        "figure",
        "average",
        "statutory",
        "corporate",
        "jurisdiction",
        "country",
        "economy",
        "year",
        "oecd",
        "rate",
    }

    for df in sheets.values():

        for _, row in df.iterrows():

            cells = [
                v
                for v in row.tolist()
                if not pd.isna(v)
            ]

            text_cells = [
                str(v).strip()
                for v in cells
                if (
                    isinstance(v, str)
                    and str(v).strip()
                )
            ]

            numeric_cells = [
                float(v)
                for v in cells
                if (
                    isinstance(
                        v,
                        (int, float)
                    )
                    and 0
                    <= float(v)
                    <= 100
                )
            ]

            if (
                not text_cells
                or not numeric_cells
            ):
                continue

            name = text_cells[0]

            if name.lower() in skip:
                continue

            if len(name) > 80:
                continue

            country = normalize_country(
                name
            )

            raw_rate = (
                numeric_cells[-1]
            )

            tax_rate = (
                raw_rate
                if raw_rate <= 1
                else raw_rate / 100
            )

            if (
                0
                <= tax_rate
                <= 0.60
            ):
                rates[
                    country
                ] = tax_rate

    if len(rates) < 20:

        raise ValueError(
            f"Only {len(rates)} "
            "OECD tax rates parsed."
        )

    return rates


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def fetch_taxes():

    content = get_bytes(
        OECD_STATLINK_URL
    )

    rates = parse_oecd_xlsx(
        content
    )

    return (
        rates,
        OECD_STATLINK_URL,
    )


# ============================================================
# 4. Trading Economics 10Y yields
# ============================================================

def slugify_country(country):

    special = {
        "United States":
            "united-states",

        "United Kingdom":
            "united-kingdom",

        "South Korea":
            "south-korea",

        "Czech Republic":
            "czech-republic",

        "Hong Kong":
            "hong-kong",

        "New Zealand":
            "new-zealand",

        "South Africa":
            "south-africa",

        "Saudi Arabia":
            "saudi-arabia",

        "United Arab Emirates":
            "united-arab-emirates",
    }

    if country in special:
        return special[
            country
        ]

    text = unicodedata.normalize(
        "NFKD",
        country,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    text = text.lower()

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    ).strip("-")


def extract_country_10y(html):

    try:

        tables = pd.read_html(
            io.StringIO(html),
            flavor="lxml",
        )

    except Exception:

        tables = []

    for df in tables:

        if (
            df.empty
            or len(df.columns) < 2
        ):
            continue

        for _, row in df.iterrows():

            label = str(
                row.iloc[0]
            ).strip()

            if (
                "10Y" in label
                and "TIPS"
                not in label.upper()
            ):

                value = parse_rate(
                    row.iloc[1]
                )

                if (
                    value is not None
                    and -0.05
                    < value
                    < 0.50
                ):
                    return value

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    for row in soup.find_all(
        "tr"
    ):

        cells = [
            cell.get_text(
                " ",
                strip=True,
            )
            for cell
            in row.find_all(
                ["td", "th"]
            )
        ]

        if len(cells) < 2:
            continue

        if (
            "10Y" in cells[0]
            and "TIPS"
            not in cells[0].upper()
        ):

            value = parse_rate(
                cells[1]
            )

            if (
                value is not None
                and -0.05
                < value
                < 0.50
            ):
                return value

    raise ValueError(
        "10Y yield not found."
    )


def try_bonds_page(country):

    html = get_text(
        TE_BONDS_URL
    )

    try:

        tables = pd.read_html(
            io.StringIO(html),
            flavor="lxml",
        )

    except Exception:

        return None

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
                if "country"
                in c.lower()
            ),
            df.columns[0],
        )

        value_col = next(
            (
                c
                for c in df.columns
                if (
                    c.lower()
                    in {
                        "last",
                        "yield"
                    }
                    or "yield"
                    in c.lower()
                )
            ),
            df.columns[1],
        )

        for _, row in df.iterrows():

            row_country = normalize_country(
                row.get(
                    country_col,
                    ""
                )
            )

            if row_country != country:
                continue

            value = parse_rate(
                row.get(
                    value_col
                )
            )

            if (
                value is not None
                and -0.05
                < value
                < 0.50
            ):
                return value

    return None


@st.cache_data(
    ttl=1800,
    show_spinner=False,
)
def fetch_te_10y(country):

    try:

        value = try_bonds_page(
            country
        )

        if value is not None:

            return (
                value,
                TE_BONDS_URL,
                now_utc(),
            )

    except Exception:

        pass

    slug = slugify_country(
        country
    )

    country_url = (
        "https://tradingeconomics.com/"
        f"{slug}/government-bond-yield"
    )

    html = get_text(
        country_url
    )

    value = extract_country_10y(
        html
    )

    return (
        value,
        country_url,
        now_utc(),
    )


# ============================================================
# Part 9 formulas
# ============================================================

def relever_beta(
    beta_u,
    tax,
    debt_share,
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
            + (1 - tax)
            * debt_to_equity
        )
    )


def calculate(
    beta_u,
    tax,
    erp,
    debt_share,
    rf_us,
    rf_f,
    spread_us,
    spread_f_override=None,
):

    beta_e = relever_beta(
        beta_u,
        tax,
        debt_share,
    )

    re_us = (
        rf_us
        + beta_e * erp
    )

    rd_us = (
        rf_us
        + spread_us
    )

    factor = (
        (1 + rf_f)
        / (1 + rf_us)
    )

    re_f = (
        (1 + re_us)
        * factor
        - 1
    )

    spread_f = (
        spread_us
        * factor

        if spread_f_override
        is None

        else
        spread_f_override
    )

    rd_f = (
        rf_f
        + spread_f
    )

    wacc_us = (
        (1 - debt_share)
        * re_us

        + debt_share
        * rd_us
        * (1 - tax)
    )

    wacc_f = (
        (1 - debt_share)
        * re_f

        + debt_share
        * rd_f
        * (1 - tax)
    )

    return {
        "beta_u": beta_u,
        "beta_e": beta_e,

        "tax": tax,
        "erp": erp,
        "debt_share": debt_share,

        "rf_us": rf_us,
        "rf_f": rf_f,

        "spread_us": spread_us,
        "spread_f": spread_f,

        "re_us": re_us,
        "rd_us": rd_us,

        "rd_us_at":
            rd_us * (1 - tax),

        "wacc_us":
            wacc_us,

        "re_f":
            re_f,

        "rd_f":
            rd_f,

        "rd_f_at":
            rd_f * (1 - tax),

        "wacc_f":
            wacc_f,

        "factor":
            factor,
    }


# ============================================================
# App title
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
# Fetch beta / BBB / tax data
# ============================================================

warnings = []


try:

    (
        betas,
        beta_source,
        beta_date,
    ) = fetch_betas()

except Exception as e:

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

    beta_source = (
        "Emergency fallback"
    )

    beta_date = (
        now_utc()
    )

    warnings.append(
        "Damodaran betas.xls "
        f"fetch failed: {e}"
    )


try:

    (
        bbb_auto,
        bbb_date,
    ) = fetch_bbb()

except Exception as e:

    bbb_auto = (
        FALLBACK_BBB
    )

    bbb_date = (
        "Emergency fallback"
    )

    warnings.append(
        "Damodaran BBB spread "
        f"fetch failed: {e}"
    )


try:

    (
        tax_rates,
        oecd_statlink,
    ) = fetch_taxes()

except Exception as e:

    tax_rates = {
        "United States":
            FALLBACK_US_TAX,

        "Colombia":
            0.35,
    }

    oecd_statlink = (
        "Emergency fallback"
    )

    warnings.append(
        "OECD corporate tax "
        f"fetch failed: {e}"
    )


for warning in warnings:

    st.warning(
        warning
        + " — manual override remains available."
    )


# ============================================================
# Selection lists
# ============================================================

industries = (
    betas["Industry"]
    .dropna()
    .astype(str)
    .tolist()
)


if (
    DEFAULT_INDUSTRY
    not in industries
):

    industries.insert(
        0,
        DEFAULT_INDUSTRY,
    )


countries = sorted(
    set(tax_rates)
    | {DEFAULT_COUNTRY}
)


# ============================================================
# Sidebar: project settings
# ============================================================

with st.sidebar:

    st.header(
        "Project settings"
    )

    industry = st.selectbox(
        "Industry",
        industries,
        index=industries.index(
            DEFAULT_INDUSTRY
        ),
    )

    country = st.selectbox(
        "Target country",
        countries,
        index=countries.index(
            DEFAULT_COUNTRY
        ),
    )

    erp = (
        st.number_input(
            "Equity risk premium (%)",
            0.0,
            20.0,
            6.5,
            0.1,
        )
        / 100
    )

    debt_share = (
        st.slider(
            "Target debt share (%)",
            0,
            95,
            30,
            1,
        )
        / 100
    )

    beta_match = (
        betas.loc[
            betas["Industry"]
            == industry,
            "Unlevered Beta",
        ]
    )

    beta_auto = (
        float(
            beta_match.iloc[0]
        )

        if len(
            beta_match
        )

        else
        FALLBACK_BETA
    )

    us_tax_auto = (
        tax_rates.get(
            "United States",
            FALLBACK_US_TAX,
        )
    )

    foreign_tax_auto = (
        tax_rates.get(
            country,
            us_tax_auto,
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
        "Override unlevered beta"
    )

    beta_manual = st.number_input(
        "Unlevered beta",
        0.0,
        5.0,
        beta_auto,
        0.001,
        disabled=not override_beta,
    )

    override_us_tax = (
        st.toggle(
            "Override U.S. tax rate"
        )
    )

    us_tax_manual = (
        st.number_input(
            "U.S. corporate tax rate (%)",
            0.0,
            60.0,
            us_tax_auto * 100,
            0.01,
            disabled=not override_us_tax,
        )
        / 100
    )

    if country != "United States":

        override_foreign_tax = (
            st.toggle(
                f"Override {country} tax rate"
            )
        )

        foreign_tax_manual = (
            st.number_input(
                f"{country} corporate tax rate (%)",
                0.0,
                60.0,
                foreign_tax_auto * 100,
                0.01,
                disabled=not override_foreign_tax,
            )
            / 100
        )

    else:

        override_foreign_tax = False
        foreign_tax_manual = us_tax_manual

    override_us_spread = (
        st.toggle(
            "Override USD BBB spread"
        )
    )

    us_spread_manual = (
        st.number_input(
            "USD BBB spread (%)",
            0.0,
            20.0,
            bbb_auto * 100,
            0.01,
            disabled=not override_us_spread,
        )
        / 100
    )


# ============================================================
# Trading Economics yields
# ============================================================

te_warnings = []


try:

    (
        rf_us_auto,
        rf_us_url,
        rf_us_date,
    ) = fetch_te_10y(
        "United States"
    )

except Exception as e:

    rf_us_auto = FALLBACK_US_10Y
    rf_us_url = TE_BONDS_URL
    rf_us_date = "Fetch failed"

    te_warnings.append(
        "U.S. 10Y yield "
        f"fetch failed: {e}"
    )


if country == "United States":

    rf_foreign_auto = rf_us_auto
    rf_foreign_url = rf_us_url
    rf_foreign_date = rf_us_date

else:

    try:

        (
            rf_foreign_auto,
            rf_foreign_url,
            rf_foreign_date,
        ) = fetch_te_10y(
            country
        )

    except Exception as e:

        rf_foreign_auto = rf_us_auto
        rf_foreign_url = TE_BONDS_URL
        rf_foreign_date = "Fetch failed"

        te_warnings.append(
            f"{country} 10Y yield "
            f"fetch failed: {e}. "
            "Use manual override."
        )


for warning in te_warnings:

    st.warning(
        warning
    )


# ============================================================
# Sidebar: yield / foreign spread overrides
# ============================================================

with st.sidebar:

    override_rf_us = (
        st.toggle(
            "Override U.S. 10Y yield"
        )
    )

    rf_us_manual = (
        st.number_input(
            "U.S. 10Y government yield (%)",
            -5.0,
            50.0,
            rf_us_auto * 100,
            0.01,
            disabled=not override_rf_us,
        )
        / 100
    )

    if country != "United States":

        override_rf_foreign = (
            st.toggle(
                f"Override {country} 10Y yield"
            )
        )

        rf_foreign_manual = (
            st.number_input(
                f"{country} 10Y government yield (%)",
                -5.0,
                50.0,
                rf_foreign_auto * 100,
                0.01,
                disabled=not override_rf_foreign,
            )
            / 100
        )

        preview_factor = (
            (1 + rf_foreign_auto)
            / (1 + rf_us_auto)
        )

        preview_spread = (
            bbb_auto
            * preview_factor
        )

        override_spread_foreign = (
            st.toggle(
                f"Override {country} BBB spread"
            )
        )

        spread_foreign_manual = (
            st.number_input(
                f"{country} BBB spread (%)",
                0.0,
                30.0,
                preview_spread * 100,
                0.01,
                disabled=not override_spread_foreign,
            )
            / 100
        )

    else:

        override_rf_foreign = False
        rf_foreign_manual = rf_us_manual
        override_spread_foreign = False
        spread_foreign_manual = None


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
    us_tax

    if country
    == "United States"

    else (
        foreign_tax_manual

        if override_foreign_tax

        else foreign_tax_auto
    )
)


tax = (
    us_tax

    if tax_choice
    == "United States"

    else foreign_tax
)


spread_us = (
    us_spread_manual
    if override_us_spread
    else bbb_auto
)


rf_us = (
    rf_us_manual
    if override_rf_us
    else rf_us_auto
)


rf_foreign = (
    rf_us

    if country
    == "United States"

    else (
        rf_foreign_manual

        if override_rf_foreign

        else rf_foreign_auto
    )
)


spread_foreign_override = (
    spread_foreign_manual

    if override_spread_foreign

    else None
)


# ============================================================
# Calculate
# ============================================================

result = calculate(
    beta_u,
    tax,
    erp,
    debt_share,
    rf_us,
    rf_foreign,
    spread_us,
    spread_foreign_override,
)


# ============================================================
# Main results
# ============================================================

st.subheader(
    f"{industry} — {country}"
)


st.write(
    f"Unlevered beta **{result['beta_u']:.3f}** · "
    f"Levered beta **{result['beta_e']:.3f}** · "
    f"ERP **{pct(result['erp'])}** · "
    f"Debt **{pct(result['debt_share'])}** · "
    f"Project tax **{pct(result['tax'])}**"
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
            result["re_us"]
        ),
    )

    b.metric(
        "WACC",
        pct(
            result["wacc_us"]
        ),
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(result['rd_us'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(result['rd_us_at'])}**"
    )

    st.write(
        "BBB spread: "
        f"**{pct(result['spread_us'])}**"
    )


with right:

    st.markdown(
        f"### 🌐 {country} currency"
    )

    a, b = st.columns(2)

    a.metric(
        "Cost of equity",
        pct(
            result["re_f"]
        ),
    )

    b.metric(
        "WACC",
        pct(
            result["wacc_f"]
        ),
    )

    st.write(
        "Pre-tax cost of debt: "
        f"**{pct(result['rd_f'])}**"
    )

    st.write(
        "After-tax cost of debt: "
        f"**{pct(result['rd_f_at'])}**"
    )

    st.write(
        "BBB spread: "
        f"**{pct(result['spread_f'])}**"
    )


# ============================================================
# Formulas
# ============================================================

with st.expander(
    "Formulas / assumptions",
    expanded=True,
):

    st.markdown(
        "**Relever beta**"
    )

    st.latex(
        r"\beta_E="
        r"\beta_U"
        r"\left["
        r"1+(1-\tau)"
        r"\frac{D}{E}"
        r"\right],"
        r"\quad "
        r"\frac{D}{E}"
        r"="
        r"\frac{d}{1-d}"
    )

    st.markdown(
        "**USD cost of equity**"
    )

    st.latex(
        r"R_e="
        r"R_f"
        r"+"
        r"\beta_E"
        r"\times ERP"
    )

    st.markdown(
        "**USD pretax borrowing cost**"
    )

    st.latex(
        r"R_d="
        r"R_f+s"
    )

    st.markdown(
        "**Foreign-currency equity cost**"
    )

    st.latex(
        r"1+R_e^*"
        r"="
        r"(1+R_e)"
        r"\frac{1+R_f^*}"
        r"{1+R_f}"
    )

    st.markdown(
        "**Foreign-currency BBB spread**"
    )

    st.latex(
        r"s^*="
        r"s"
        r"\frac{1+R_f^*}"
        r"{1+R_f}"
    )

    st.markdown(
        "**Foreign-currency pretax borrowing cost**"
    )

    st.latex(
        r"R_d^*="
        r"R_f^*+s^*"
    )

    st.markdown(
        "**WACC**"
    )

    st.latex(
        r"WACC="
        r"(1-d)R_e"
        r"+"
        r"dR_d(1-\tau)"
    )


# ============================================================
# Calculation detail
# ============================================================

st.subheader(
    "Calculation detail"
)


detail = pd.DataFrame(
    {
        "Input / output": [
            "Unlevered beta",
            "Levered beta",
            "Equity risk premium",
            "Debt share",
            "Project tax rate",
            "U.S. 10Y yield",
            f"{country} 10Y yield",
            "USD BBB spread",
            f"{country} BBB spread",
            "USD cost of equity",
            f"{country} cost of equity",
            "USD pretax cost of debt",
            f"{country} pretax cost of debt",
            "USD WACC",
            f"{country} WACC",
        ],

        "Value": [
            f"{result['beta_u']:.4f}",
            f"{result['beta_e']:.4f}",
            pct(result["erp"]),
            pct(result["debt_share"]),
            pct(result["tax"]),
            pct(result["rf_us"]),
            pct(result["rf_f"]),
            pct(result["spread_us"]),
            pct(result["spread_f"]),
            pct(result["re_us"]),
            pct(result["re_f"]),
            pct(result["rd_us"]),
            pct(result["rd_f"]),
            pct(result["wacc_us"]),
            pct(result["wacc_f"]),
        ],
    }
)


st.dataframe(
    detail,
    hide_index=True,
    use_container_width=True,
)


# ============================================================
# All-industry comparison
# ============================================================

st.subheader(
    "All-industry comparison"
)


rows = []


for _, row in betas.iterrows():

    industry_result = calculate(
        float(
            row["Unlevered Beta"]
        ),
        tax,
        erp,
        debt_share,
        rf_us,
        rf_foreign,
        spread_us,
        spread_foreign_override,
    )

    rows.append(
        {
            "Industry":
                row["Industry"],

            "Unlevered Beta":
                industry_result["beta_u"],

            "Levered Beta":
                industry_result["beta_e"],

            "USD Cost of Equity":
                industry_result["re_us"],

            "USD WACC":
                industry_result["wacc_us"],

            f"{country} Cost of Equity":
                industry_result["re_f"],

            f"{country} WACC":
                industry_result["wacc_f"],
        }
    )


all_df = pd.DataFrame(
    rows
)


show_df = all_df.copy()


for column in show_df.columns:

    if (
        "Cost of Equity"
        in column

        or "WACC"
        in column
    ):

        show_df[
            column
        ] = (
            show_df[
                column
            ]
            .map(pct)
        )


st.dataframe(
    show_df,
    hide_index=True,
    use_container_width=True,
    height=420,
)


# ============================================================
# Downloads
# ============================================================

c1, c2 = st.columns(2)


selected_csv = (
    pd.DataFrame(
        [
            {
                "Industry":
                    industry,

                "Target Country":
                    country,

                **result,
            }
        ]
    )
    .to_csv(
        index=False
    )
    .encode(
        "utf-8"
    )
)


all_csv = (
    all_df
    .to_csv(
        index=False
    )
    .encode(
        "utf-8"
    )
)


c1.download_button(
    "⬇️ Download selected result",
    selected_csv,
    "selected_cost_of_capital.csv",
    "text/csv",
    use_container_width=True,
)


c2.download_button(
    "⬇️ Download all industries",
    all_csv,
    "all_industries_cost_of_capital.csv",
    "text/csv",
    use_container_width=True,
)


# ============================================================
# Sources and dates
# ============================================================

st.subheader(
    "Sources and dates"
)


sources = pd.DataFrame(
    [
        {
            "Input":
                "Industry unlevered beta",

            "Source":
                beta_source,

            "Date / status":
                beta_date,

            "Professor URL":
                BETAS_XLS_URL,
        },

        {
            "Input":
                "Corporate tax rate",

            "Source":
                "OECD Corporate Tax Statistics 2024",

            "Date / status":
                "2024 statutory rate data",

            "Professor URL":
                OECD_PAGE_URL,
        },

        {
            "Input":
                "USD BBB spread",

            "Source":
                "Damodaran Baa2/BBB, large non-financial",

            "Date / status":
                bbb_date,

            "Professor URL":
                RATINGS_URL,
        },

        {
            "Input":
                "U.S. 10Y yield",

            "Source":
                "Trading Economics",

            "Date / status":
                rf_us_date,

            "Professor URL":
                TE_BONDS_URL,
        },

        {
            "Input":
                f"{country} 10Y yield",

            "Source":
                "Trading Economics",

            "Date / status":
                rf_foreign_date,

            "Professor URL":
                TE_BONDS_URL,
        },
    ]
)


st.dataframe(
    sources,
    hide_index=True,
    use_container_width=True,
)


with st.expander(
    "Actual retrieval URLs"
):

    st.write(
        "OECD official Statlink used for the tax table: "
        f"{oecd_statlink}"
    )

    st.write(
        "U.S. 10Y retrieval URL: "
        f"{rf_us_url}"
    )

    st.write(
        f"{country} 10Y retrieval URL: "
        f"{rf_foreign_url}"
    )


st.caption(
    "The app uses the professor-provided source links. "
    "The OECD corporate-tax table is downloaded through "
    "the official Statlink underlying the professor-provided OECD page. "
    "Manual overrides remain available if a live source cannot be fetched."
)
