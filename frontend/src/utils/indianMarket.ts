/**
 * Indian Capital Markets Formatting & Instrument Reference Utilities
 * Strict NSE/BSE quant conventions, INR currency grouping, and Indian numbering (Lakhs & Crores).
 */

export const INDIAN_EQUITY_NAMES: Record<string, string> = {
  "RELIANCE.NS": "Reliance Industries Ltd.",
  "TCS.NS": "Tata Consultancy Services Ltd.",
  "HDFCBANK.NS": "HDFC Bank Ltd.",
  "INFY.NS": "Infosys Ltd.",
  "ICICIBANK.NS": "ICICI Bank Ltd.",
  "SBIN.NS": "State Bank of India",
  "BHARTIARTL.NS": "Bharti Airtel Ltd.",
  "ITC.NS": "ITC Ltd.",
  "KOTAKBANK.NS": "Kotak Mahindra Bank Ltd.",
  "LT.NS": "Larsen & Toubro Ltd.",
  "AXISBANK.NS": "Axis Bank Ltd.",
  "HINDUNILVR.NS": "Hindustan Unilever Ltd.",
  "BAJFINANCE.NS": "Bajaj Finance Ltd.",
  "MARUTI.NS": "Maruti Suzuki India Ltd.",
  "ASIANPAINT.NS": "Asian Paints Ltd.",
  "HCLTECH.NS": "HCL Technologies Ltd.",
  "SUNPHARMA.NS": "Sun Pharmaceutical Ind. Ltd.",
  "TITAN.NS": "Titan Company Ltd.",
  "ULTRACEMCO.NS": "UltraTech Cement Ltd.",
  "TATASTEEL.NS": "Tata Steel Ltd.",
  "NTPC.NS": "NTPC Ltd.",
  "POWERGRID.NS": "Power Grid Corp of India Ltd.",
  "ONGC.NS": "Oil & Natural Gas Corp Ltd.",
  "M&M.NS": "Mahindra & Mahindra Ltd.",
  "JSWSTEEL.NS": "JSW Steel Ltd.",
  "COALINDIA.NS": "Coal India Ltd.",
  "BAJAJFINSV.NS": "Bajaj Finserv Ltd.",
  "ADANIENT.NS": "Adani Enterprises Ltd.",
  "ADANIPORTS.NS": "Adani Ports & SEZ Ltd.",
  "BPCL.NS": "Bharat Petroleum Corp Ltd.",
  "GRASIM.NS": "Grasim Industries Ltd.",
  "CIPLA.NS": "Cipla Ltd.",
  "NESTLEIND.NS": "Nestle India Ltd.",
  "WIPRO.NS": "Wipro Ltd.",
  "TATACONSUM.NS": "Tata Consumer Products Ltd.",
  "DRREDDY.NS": "Dr. Reddy's Laboratories Ltd.",
  "EICHERMOT.NS": "Eicher Motors Ltd.",
  "HEROMOTOCO.NS": "Hero MotoCorp Ltd.",
  "DIVISLAB.NS": "Divi's Laboratories Ltd.",
  "HINDALCO.NS": "Hindalco Industries Ltd.",
  "APOLLOHOSP.NS": "Apollo Hospitals Enterprise Ltd.",
  "SHRIRAMFIN.NS": "Shriram Finance Ltd.",
  "TRENT.NS": "Trent Ltd.",
  "BEL.NS": "Bharat Electronics Ltd.",
  "BRITANNIA.NS": "Britannia Industries Ltd.",
  "SBILIFE.NS": "SBI Life Insurance Co. Ltd.",
  "HDFCLIFE.NS": "HDFC Life Insurance Co. Ltd.",
  "TECHM.NS": "Tech Mahindra Ltd.",
  "BAJAJ-AUTO.NS": "Bajaj Auto Ltd.",
  "INDUSINDBK.NS": "IndusInd Bank Ltd.",
};

export const SECTOR_BY_TICKER: Record<string, string> = {
  "RELIANCE.NS": "Energy & Petrochemicals",
  "TCS.NS": "Information Technology",
  "HDFCBANK.NS": "Financial Services",
  "INFY.NS": "Information Technology",
  "ICICIBANK.NS": "Financial Services",
  "SBIN.NS": "Financial Services",
  "BHARTIARTL.NS": "Telecommunications",
  "ITC.NS": "FMCG & Consumer Goods",
  "KOTAKBANK.NS": "Financial Services",
  "LT.NS": "Capital Goods & Infra",
  "AXISBANK.NS": "Financial Services",
  "HINDUNILVR.NS": "FMCG & Consumer Goods",
  "BAJFINANCE.NS": "Financial Services",
  "MARUTI.NS": "Automobile & Auto Parts",
  "ASIANPAINT.NS": "Consumer Discretionary",
  "HCLTECH.NS": "Information Technology",
  "SUNPHARMA.NS": "Healthcare & Pharma",
  "TITAN.NS": "Consumer Discretionary",
  "ULTRACEMCO.NS": "Materials & Cement",
  "TATASTEEL.NS": "Metals & Mining",
  "NTPC.NS": "Utilities & Power",
  "POWERGRID.NS": "Utilities & Power",
  "ONGC.NS": "Energy & Oil",
  "M&M.NS": "Automobile & Auto Parts",
  "JSWSTEEL.NS": "Metals & Mining",
  "COALINDIA.NS": "Metals & Mining",
  "BAJAJFINSV.NS": "Financial Services",
  "ADANIENT.NS": "Conglomerate & Infra",
  "ADANIPORTS.NS": "Services & Logistics",
  "BPCL.NS": "Energy & Oil",
  "GRASIM.NS": "Materials & Cement",
  "CIPLA.NS": "Healthcare & Pharma",
  "NESTLEIND.NS": "FMCG & Consumer Goods",
  "WIPRO.NS": "Information Technology",
  "TATACONSUM.NS": "FMCG & Consumer Goods",
  "DRREDDY.NS": "Healthcare & Pharma",
  "EICHERMOT.NS": "Automobile & Auto Parts",
  "HEROMOTOCO.NS": "Automobile & Auto Parts",
  "DIVISLAB.NS": "Healthcare & Pharma",
  "HINDALCO.NS": "Metals & Mining",
  "APOLLOHOSP.NS": "Healthcare & Pharma",
  "SHRIRAMFIN.NS": "Financial Services",
  "TRENT.NS": "Consumer Discretionary",
  "BEL.NS": "Aerospace & Defense",
  "BRITANNIA.NS": "FMCG & Consumer Goods",
  "SBILIFE.NS": "Financial Services",
  "HDFCLIFE.NS": "Financial Services",
  "TECHM.NS": "Information Technology",
  "BAJAJ-AUTO.NS": "Automobile & Auto Parts",
  "INDUSINDBK.NS": "Financial Services",
};

/**
 * Resolves full company name from ticker symbol with .NS/.BO fallback.
 */
export function getInstrumentName(ticker: string): string {
  if (!ticker) return "Indian Equity";
  if (INDIAN_EQUITY_NAMES[ticker]) return INDIAN_EQUITY_NAMES[ticker];
  const clean = ticker.replace(/\.(NS|BO)$/i, "");
  return INDIAN_EQUITY_NAMES[`${clean}.NS`] || `${clean} Equity`;
}

/**
 * Resolves industry sector from ticker symbol.
 */
export function getInstrumentSector(ticker: string): string {
  if (!ticker) return "Indian Equities";
  if (SECTOR_BY_TICKER[ticker]) return SECTOR_BY_TICKER[ticker];
  const clean = ticker.replace(/\.(NS|BO)$/i, "");
  return SECTOR_BY_TICKER[`${clean}.NS`] || "Indian Equities";
}

/**
 * Formats a numeric value into standard Indian currency formatting (en-IN).
 * Examples: 100000 -> ₹1,00,000.00, -5240.5 -> -₹5,240.50
 */
export function formatINR(
  val: number | null | undefined,
  options?: {
    showSign?: boolean;
    decimals?: number;
    showSymbol?: boolean;
  }
): string {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  const decimals = options?.decimals ?? 2;
  const isNegative = val < 0;
  const absVal = Math.abs(val);
  const symbol = options?.showSymbol !== false ? "₹" : "";

  const formatted = absVal.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  if (isNegative) {
    return `-${symbol}${formatted}`;
  }
  if (options?.showSign && val > 0) {
    return `+${symbol}${formatted}`;
  }
  return `${symbol}${formatted}`;
}

/**
 * Formats a numeric value into standard Indian compact numbering:
 * Crores (Cr >= 1,00,00,000) or Lakhs (L >= 1,00,000).
 * Examples: 5000000 -> ₹50.00 L, 25000000 -> ₹2.50 Cr
 */
export function formatIndianCompact(
  val: number | null | undefined,
  options?: { showSign?: boolean; showSymbol?: boolean }
): string {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  const absVal = Math.abs(val);
  const isNegative = val < 0;
  const symbol = options?.showSymbol !== false ? "₹" : "";

  let prefix = "";
  if (isNegative) {
    prefix = "-";
  } else if (options?.showSign && val > 0) {
    prefix = "+";
  }

  // 1 Crore = 1,00,00,000 (10^7)
  if (absVal >= 10000000) {
    const cr = absVal / 10000000;
    return `${prefix}${symbol}${cr.toFixed(2)} Cr`;
  }
  // 1 Lakh = 1,00,000 (10^5)
  if (absVal >= 100000) {
    const lk = absVal / 100000;
    return `${prefix}${symbol}${lk.toFixed(2)} L`;
  }
  if (absVal >= 1000) {
    const k = absVal / 1000;
    return `${prefix}${symbol}${k.toFixed(1)} K`;
  }
  return `${prefix}${symbol}${absVal.toFixed(2)}`;
}
