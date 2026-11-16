# International Cost of Capital App

This Streamlit app compares a project's cost of equity and WACC in USD and in the currency of a selected country.

## Features

The app:

- Retrieves U.S. industry unlevered betas from Aswath Damodaran
- Retrieves the Baa2/BBB USD borrowing spread from Damodaran
- Retrieves corporate tax rates from OECD Corporate Tax Statistics
- Retrieves 10-year government bond yields from Trading Economics
- Allows the user to select an industry and target country
- Allows the user to change the equity risk premium and target debt share
- Allows manual overrides of all major source inputs
- Calculates cost of equity, cost of debt, and WACC in USD and foreign currency
- Displays an all-industry comparison
- Allows CSV download
- Includes required verification checks
- Includes a data refresh button

## Default Settings

- Industry: Software (System & Application)
- Country: United States
- Tax rate: U.S. corporate tax rate
- Equity risk premium: 6.5%
- Debt share: 30%

## Main Formulas

### Levered Beta

beta_L = beta_U × [1 + (1 - tax rate) × D/E]

where:

D/E = Debt Share / (1 - Debt Share)

### USD Cost of Equity

Cost of Equity (USD)
= U.S. 10-Year Government Yield
+ Levered Beta × Equity Risk Premium

### USD Cost of Debt

Pre-Tax Cost of Debt (USD)
= U.S. 10-Year Government Yield
+ BBB Borrowing Spread

### Foreign Currency Conversion

1 + Foreign Currency Rate

= (1 + USD Rate)
× (1 + Foreign Government Yield)
÷ (1 + U.S. Government Yield)

### WACC

WACC

= Equity Weight × Cost of Equity

+ Debt Weight × Pre-Tax Cost of Debt × (1 - Tax Rate)

## Foreign BBB Spread

When the foreign BBB spread override is switched off, the app first converts the full USD pre-tax borrowing cost into the foreign currency.

It then calculates:

Foreign BBB Spread
= Foreign Pre-Tax Borrowing Cost
- Foreign Government Yield

This method reproduces the cost-of-capital approach discussed in class.

## Verification

The app automatically checks:

1. Equal government bond yields produce equal USD and foreign-currency results when the foreign BBB spread override is off.

2. If debt share is zero, WACC equals cost of equity.

3. Changing only the foreign BBB spread override leaves the USD results unchanged.

## Data Sources

Industry Betas:

https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls

BBB Borrowing Spread:

https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html

OECD Corporate Tax Rates:

https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html

Trading Economics Government Bond Yields:

https://tradingeconomics.com/bonds

## Notes

This app uses simplified formulas discussed in class.

External websites may occasionally change their page structure or block automated requests. Manual override controls are therefore provided for all major inputs.
