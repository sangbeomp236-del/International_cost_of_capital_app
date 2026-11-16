# International Cost of Capital App

This Streamlit app compares a project's cost of equity and WACC in USD and in the currency of a selected country.

## Default Settings

- Industry: Software (System & Application)
- Target country: United States
- Project tax rate: U.S. tax rate
- Equity risk premium: 6.5%
- Target debt share: 30%

## Data Sources

The app uses the sources provided in the assignment.

### Industry Unlevered Beta

Aswath Damodaran:

https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls

The app downloads and reads the Damodaran Excel file directly and uses the Unlevered Beta for the selected U.S. industry.

A copy of `betas.xls` can also be stored in the GitHub repository as a backup if the live download fails.

### Corporate Tax Rates

OECD Corporate Tax Statistics 2024:

https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html#chapter-d1e2342-08e74a33fb

The app follows the official Figure 2.1 Statlink from this page and retrieves the statutory corporate income tax rates.

### USD BBB Borrowing Spread

Aswath Damodaran:

https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html

The app uses the Baa2/BBB default spread for large non-financial service firms.

### 10-Year Government Bond Yields

Trading Economics:

https://tradingeconomics.com/bonds

The app first attempts to retrieve the data from the professor-provided bonds page.

If that page is rendered dynamically, the app follows the corresponding country government-bond page on the same Trading Economics website.

## Main Formulas

### Relevered Beta

beta_E = beta_U × [1 + (1 - tax rate) × D/E]

where:

D/E = Debt Share / (1 - Debt Share)

### USD Cost of Equity

Re = Rf + beta_E × ERP

### USD Pretax Borrowing Cost

Rd = Rf + s

where `s` is the USD BBB borrowing spread.

### Foreign-Currency Cost of Equity

1 + Re* = (1 + Re) × (1 + Rf*) / (1 + Rf)

### Foreign-Currency BBB Spread

s* = s × (1 + Rf*) / (1 + Rf)

### Foreign-Currency Pretax Borrowing Cost

Rd* = Rf* + s*

### WACC

WACC = (1 - d) × Re + d × Rd × (1 - tax rate)

## Verification

The app automatically verifies the following:

1. Equal U.S. and foreign government bond yields produce equal USD and foreign-currency results when the foreign BBB spread override is off.

2. When debt share is zero, WACC equals cost of equity.

3. Overriding the foreign-currency BBB spread does not change the USD results.

The app also reproduces the Colombia example discussed in class:

- Unlevered beta: 0.80
- Debt share: 30%
- Tax rate: 35%
- ERP: 6.5%
- U.S. 10-year yield: 4.0%
- Colombia 10-year yield: 12.0%
- USD borrowing spread: 1.5%

Expected results:

- Levered beta: 1.0229
- USD cost of equity: 10.6486%
- USD pretax cost of debt: 5.5000%
- USD WACC: 8.5265%
- COP cost of equity: 19.1600%
- COP BBB spread: 1.6154%
- COP pretax cost of debt: 13.6154%
- COP WACC: 16.0670%

## Manual Overrides

Users may manually override:

- Unlevered beta
- U.S. corporate tax rate
- Selected-country corporate tax rate
- USD BBB spread
- U.S. 10-year government yield
- Selected-country 10-year government yield
- Selected-country BBB spread

## Other Features

- Refresh source data button
- Industry selection
- Country selection
- Adjustable ERP
- Adjustable target debt share
- U.S. versus foreign tax-rate selection
- Side-by-side USD and foreign-currency results
- All-industry comparison
- CSV download
- Source and date display
