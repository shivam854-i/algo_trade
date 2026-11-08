/**
 * Indian Capital Markets Formatting & Instrument Reference Utilities
 * Strict NSE/BSE quant conventions, INR currency grouping, and Indian numbering (Lakhs & Crores).
 */

export interface NSEInstrument {
  ticker: string;
  name: string;
  sector: string;
  index: "NIFTY_50" | "NIFTY_NEXT_50" | "NIFTY_MIDCAP" | "SENSEX";
  marketCapTier: "Large Cap" | "Mid Cap" | "Small Cap";
  exchange: "NSE" | "BSE";
  basePrice?: number;
}

export const NSE_MASTER_DIRECTORY: NSEInstrument[] = [
  // NIFTY 50 Blue Chips
  { ticker: "RELIANCE.NS", name: "Reliance Industries Ltd.", sector: "Energy & Oil/Gas", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1324.0 },
  { ticker: "TCS.NS", name: "Tata Consultancy Services Ltd.", sector: "Information Technology", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2498.8 },
  { ticker: "HDFCBANK.NS", name: "HDFC Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 784.1 },
  { ticker: "INFY.NS", name: "Infosys Ltd.", sector: "Information Technology", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1171.6 },
  { ticker: "ICICIBANK.NS", name: "ICICI Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1565.0 },
  { ticker: "SBIN.NS", name: "State Bank of India (SBI)", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 812.4 },
  { ticker: "BHARTIARTL.NS", name: "Bharti Airtel Ltd.", sector: "Telecom", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1680.5 },
  { ticker: "ITC.NS", name: "ITC Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 485.2 },
  { ticker: "KOTAKBANK.NS", name: "Kotak Mahindra Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1740.0 },
  { ticker: "LT.NS", name: "Larsen & Toubro Ltd.", sector: "Infrastructure", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 3560.0 },
  { ticker: "AXISBANK.NS", name: "Axis Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1145.0 },
  { ticker: "HINDUNILVR.NS", name: "Hindustan Unilever Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2420.0 },
  { ticker: "BAJFINANCE.NS", name: "Bajaj Finance Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 6850.0 },
  { ticker: "MARUTI.NS", name: "Maruti Suzuki India Ltd.", sector: "Automobiles", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 11200.0 },
  { ticker: "ASIANPAINT.NS", name: "Asian Paints Ltd.", sector: "Consumer Tech", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2380.0 },
  { ticker: "HCLTECH.NS", name: "HCL Technologies Ltd.", sector: "Information Technology", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1840.0 },
  { ticker: "SUNPHARMA.NS", name: "Sun Pharmaceutical Ind. Ltd.", sector: "Pharmaceuticals", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1760.0 },
  { ticker: "TITAN.NS", name: "Titan Company Ltd.", sector: "Consumer Tech", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 3240.0 },
  { ticker: "ULTRACEMCO.NS", name: "UltraTech Cement Ltd.", sector: "Infrastructure", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 11150.0 },
  { ticker: "TATASTEEL.NS", name: "Tata Steel Ltd.", sector: "Metals & Mining", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 148.5 },
  { ticker: "NTPC.NS", name: "NTPC Ltd.", sector: "Energy & Power", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 382.0 },
  { ticker: "POWERGRID.NS", name: "Power Grid Corp of India Ltd.", sector: "Energy & Power", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 318.5 },
  { ticker: "ONGC.NS", name: "Oil & Natural Gas Corp Ltd.", sector: "Energy & Oil/Gas", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 262.0 },
  { ticker: "M&M.NS", name: "Mahindra & Mahindra Ltd.", sector: "Automobiles", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2880.0 },
  { ticker: "JSWSTEEL.NS", name: "JSW Steel Ltd.", sector: "Metals & Mining", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 945.0 },
  { ticker: "COALINDIA.NS", name: "Coal India Ltd.", sector: "Energy & Power", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 428.0 },
  { ticker: "BAJAJFINSV.NS", name: "Bajaj Finserv Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1610.0 },
  { ticker: "ADANIENT.NS", "name": "Adani Enterprises Ltd.", sector: "Infrastructure", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2980.0 },
  { ticker: "ADANIPORTS.NS", name: "Adani Ports & SEZ Ltd.", sector: "Infrastructure", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1320.0 },
  { ticker: "BPCL.NS", name: "Bharat Petroleum Corp Ltd.", sector: "Energy & Oil/Gas", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 315.0 },
  { ticker: "GRASIM.NS", name: "Grasim Industries Ltd.", sector: "Infrastructure", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2540.0 },
  { ticker: "CIPLA.NS", name: "Cipla Ltd.", sector: "Pharmaceuticals", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1520.0 },
  { ticker: "NESTLEIND.NS", name: "Nestle India Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2280.0 },
  { ticker: "WIPRO.NS", name: "Wipro Ltd.", sector: "Information Technology", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 565.0 },
  { ticker: "TATACONSUM.NS", name: "Tata Consumer Products Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 980.0 },
  { ticker: "DRREDDY.NS", name: "Dr. Reddy's Laboratories Ltd.", sector: "Pharmaceuticals", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1260.0 },
  { ticker: "EICHERMOT.NS", name: "Eicher Motors Ltd.", sector: "Automobiles", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 4720.0 },
  { ticker: "HEROMOTOCO.NS", name: "Hero MotoCorp Ltd.", sector: "Automobiles", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 4890.0 },
  { ticker: "DIVISLAB.NS", name: "Divi's Laboratories Ltd.", sector: "Pharmaceuticals", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 5820.0 },
  { ticker: "HINDALCO.NS", name: "Hindalco Industries Ltd.", sector: "Metals & Mining", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 655.0 },
  { ticker: "APOLLOHOSP.NS", name: "Apollo Hospitals Enterprise Ltd.", sector: "Pharmaceuticals", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 6940.0 },
  { ticker: "SHRIRAMFIN.NS", name: "Shriram Finance Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 3260.0 },
  { ticker: "TRENT.NS", name: "Trent Ltd.", sector: "Consumer Tech", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 6750.0 },
  { ticker: "BEL.NS", name: "Bharat Electronics Ltd.", sector: "Defense & Aerospace", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 298.0 },
  { ticker: "BRITANNIA.NS", name: "Britannia Industries Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 4980.0 },
  { ticker: "SBILIFE.NS", name: "SBI Life Insurance Co. Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1540.0 },
  { ticker: "HDFCLIFE.NS", name: "HDFC Life Insurance Co. Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 675.0 },
  { ticker: "TECHM.NS", name: "Tech Mahindra Ltd.", sector: "Information Technology", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1680.0 },
  { ticker: "BAJAJ-AUTO.NS", name: "Bajaj Auto Ltd.", sector: "Automobiles", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 9480.0 },
  { ticker: "INDUSINDBK.NS", name: "IndusInd Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1040.0 },

  // NIFTY NEXT 50 High Growth & Leaders
  { ticker: "HAL.NS", name: "Hindustan Aeronautics Ltd.", sector: "Defense & Aerospace", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 4320.0 },
  { ticker: "ZOMATO.NS", name: "Zomato Ltd.", sector: "Consumer Tech", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 265.0 },
  { ticker: "JIOFIN.NS", name: "Jio Financial Services Ltd.", sector: "Banking & Finance", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 318.0 },
  { ticker: "TATAPOWER.NS", name: "Tata Power Company Ltd.", sector: "Energy & Power", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 412.0 },
  { ticker: "POLYCAB.NS", name: "Polycab India Ltd.", sector: "Infrastructure", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 6840.0 },
  { ticker: "IRFC.NS", name: "Indian Railway Finance Corp", sector: "Railways", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 148.0 },
  { ticker: "CHOLAFIN.NS", name: "Cholamandalam Investment & Fin", sector: "Banking & Finance", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1280.0 },
  { ticker: "PERSISTENT.NS", name: "Persistent Systems Ltd.", sector: "Information Technology", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 5460.0 },
  { ticker: "MAXHEALTH.NS", name: "Max Healthcare Institute", sector: "Pharmaceuticals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 980.0 },
  { ticker: "DIXON.NS", name: "Dixon Technologies India", sector: "Consumer Tech", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 14600.0 },
  { ticker: "PIDILITIND.NS", name: "Pidilite Industries Ltd.", sector: "Chemicals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 3080.0 },
  { ticker: "VEDL.NS", name: "Vedanta Ltd.", sector: "Metals & Mining", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 462.0 },
  { ticker: "SIEMENS.NS", name: "Siemens India Ltd.", sector: "Infrastructure", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 7120.0 },
  { ticker: "ABB.NS", name: "ABB India Ltd.", sector: "Infrastructure", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 7480.0 },
  { ticker: "HAVELLS.NS", name: "Havells India Ltd.", sector: "Consumer Tech", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1740.0 },
  { ticker: "DLF.NS", name: "DLF Ltd.", sector: "Realty", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 840.0 },
  { ticker: "GODREJPROP.NS", name: "Godrej Properties Ltd.", sector: "Realty", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2840.0 },
  { ticker: "AMBUJACEM.NS", name: "Ambuja Cements Ltd.", sector: "Infrastructure", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 560.0 },
  { ticker: "BANKBARODA.NS", name: "Bank of Baroda", sector: "Banking & Finance", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 242.0 },
  { ticker: "PNB.NS", name: "Punjab National Bank", sector: "Banking & Finance", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 104.0 },
  { ticker: "CANBK.NS", name: "Canara Bank", sector: "Banking & Finance", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 102.0 },
  { ticker: "GAIL.NS", name: "GAIL (India) Ltd.", sector: "Energy & Oil/Gas", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 204.0 },
  { ticker: "IOC.NS", name: "Indian Oil Corporation", sector: "Energy & Oil/Gas", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 142.0 },
  { ticker: "INDIGO.NS", name: "InterGlobe Aviation (IndiGo)", sector: "Infrastructure", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 4260.0 },
  { ticker: "MOTHERSON.NS", name: "Samvardhana Motherson Int.", sector: "Automobiles", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 168.0 },
  { ticker: "LTIM.NS", name: "LTIMindtree Ltd.", sector: "Information Technology", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 5890.0 },
  { ticker: "NAUKRI.NS", name: "Info Edge (India) Ltd.", sector: "Consumer Tech", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 7850.0 },
  { ticker: "MARICO.NS", name: "Marico Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 642.0 },
  { ticker: "DABUR.NS", name: "Dabur India Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 512.0 },
  { ticker: "TORNTPHARM.NS", name: "Torrent Pharmaceuticals", sector: "Pharmaceuticals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 3240.0 },
  { ticker: "ZYDUSLIFE.NS", name: "Zydus Lifesciences Ltd.", sector: "Pharmaceuticals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 1010.0 },
  { ticker: "LUPIN.NS", name: "Lupin Ltd.", sector: "Pharmaceuticals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2180.0 },
  { ticker: "VBL.NS", name: "Varun Beverages Ltd.", sector: "Fast Moving Consumer Goods", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 620.0 },
  { ticker: "SRF.NS", name: "SRF Ltd.", sector: "Chemicals", index: "NIFTY_NEXT_50", marketCapTier: "Large Cap", exchange: "NSE", basePrice: 2360.0 },

  // NIFTY Midcap & Smallcap Momentum Stocks
  { ticker: "SUZLON.NS", name: "Suzlon Energy Ltd.", sector: "Energy & Power", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 64.5 },
  { ticker: "RVNL.NS", name: "Rail Vikas Nigam Ltd.", sector: "Railways", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 420.0 },
  { ticker: "IRCTC.NS", name: "Indian Railway Catering & Tour", sector: "Railways", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 810.0 },
  { ticker: "MAZDOCK.NS", name: "Mazagon Dock Shipbuilders", sector: "Defense & Aerospace", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 4420.0 },
  { ticker: "COCHINSHIP.NS", name: "Cochin Shipyard Ltd.", sector: "Defense & Aerospace", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1560.0 },
  { ticker: "FEDERALBNK.NS", name: "The Federal Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 198.0 },
  { ticker: "IDFCFIRSTB.NS", name: "IDFC First Bank Ltd.", sector: "Banking & Finance", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 67.5 },
  { ticker: "AUBANK.NS", name: "AU Small Finance Bank", sector: "Banking & Finance", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 590.0 },
  { ticker: "ASHOKLEY.NS", name: "Ashok Leyland Ltd.", sector: "Automobiles", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 224.0 },
  { ticker: "BHARATFORG.NS", name: "Bharat Forge Ltd.", sector: "Automobiles", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1380.0 },
  { ticker: "TATAELXSI.NS", name: "Tata Elxsi Ltd.", sector: "Information Technology", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 6680.0 },
  { ticker: "KPITTECH.NS", name: "KPIT Technologies Ltd.", sector: "Information Technology", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1420.0 },
  { ticker: "COFORGE.NS", name: "Coforge Ltd.", sector: "Information Technology", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 8450.0 },
  { ticker: "MPHASIS.NS", name: "Mphasis Ltd.", sector: "Information Technology", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 2940.0 },
  { ticker: "DEEPAKNTR.NS", name: "Deepak Nitrite Ltd.", sector: "Chemicals", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 2680.0 },
  { ticker: "TATACHEM.NS", name: "Tata Chemicals Ltd.", sector: "Chemicals", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1040.0 },
  { ticker: "BIOCON.NS", name: "Biocon Ltd.", sector: "Pharmaceuticals", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 345.0 },
  { ticker: "VOLTAS.NS", name: "Voltas Ltd.", sector: "Consumer Tech", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1720.0 },
  { ticker: "PRESTIGE.NS", name: "Prestige Estates Projects", sector: "Realty", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1680.0 },
  { ticker: "OBEROIRLTY.NS", name: "Oberoi Realty Ltd.", sector: "Realty", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 1980.0 },
  { ticker: "NHPC.NS", name: "NHPC Ltd.", sector: "Energy & Power", index: "NIFTY_MIDCAP", marketCapTier: "Mid Cap", exchange: "NSE", basePrice: 82.0 },
];

// Mapping of Ticker to Full Company Name
export const INDIAN_EQUITY_NAMES: Record<string, string> = {
  ...Object.fromEntries(NSE_MASTER_DIRECTORY.map((i) => [i.ticker, i.name])),
  // BSE 30 Aliases
  "RELIANCE.BO": "Reliance Industries Ltd. (BSE)",
  "TCS.BO": "Tata Consultancy Services (BSE)",
  "HDFCBANK.BO": "HDFC Bank Ltd. (BSE)",
  "INFY.BO": "Infosys Ltd. (BSE)",
  "ICICIBANK.BO": "ICICI Bank Ltd. (BSE)",
  "SBIN.BO": "State Bank of India (BSE)",
  "BHARTIARTL.BO": "Bharti Airtel Ltd. (BSE)",
  "ITC.BO": "ITC Ltd. (BSE)",
  "KOTAKBANK.BO": "Kotak Mahindra Bank (BSE)",
  "LT.BO": "Larsen & Toubro Ltd. (BSE)",
};

// Mapping of Ticker to Industry Sector
export const SECTOR_BY_TICKER: Record<string, string> = {
  ...Object.fromEntries(NSE_MASTER_DIRECTORY.map((i) => [i.ticker, i.sector])),
  "RELIANCE.BO": "Energy & Oil/Gas",
  "TCS.BO": "Information Technology",
  "HDFCBANK.BO": "Banking & Finance",
  "INFY.BO": "Information Technology",
  "ICICIBANK.BO": "Banking & Finance",
  "SBIN.BO": "Banking & Finance",
  "BHARTIARTL.BO": "Telecom",
  "ITC.BO": "Fast Moving Consumer Goods",
  "KOTAKBANK.BO": "Banking & Finance",
  "LT.BO": "Infrastructure",
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
 * Returns all organized instruments in the master catalog.
 */
export function getAllNSEInstruments(): NSEInstrument[] {
  return [...NSE_MASTER_DIRECTORY];
}

/**
 * Returns instruments filtered by index category.
 */
export function getInstrumentsByIndex(indexId: string): NSEInstrument[] {
  if (indexId === "ALL") return [...NSE_MASTER_DIRECTORY];
  return NSE_MASTER_DIRECTORY.filter((i) => i.index === indexId);
}

/**
 * Returns instruments filtered by industry sector.
 */
export function getInstrumentsBySector(sector: string): NSEInstrument[] {
  if (sector === "ALL") return [...NSE_MASTER_DIRECTORY];
  return NSE_MASTER_DIRECTORY.filter((i) => i.sector === sector);
}

/**
 * Returns instruments filtered by market cap tier.
 */
export function getInstrumentsByCap(tier: string): NSEInstrument[] {
  if (tier === "ALL") return [...NSE_MASTER_DIRECTORY];
  return NSE_MASTER_DIRECTORY.filter((i) => i.marketCapTier === tier);
}

/**
 * Searches instruments by ticker, name, or sector.
 */
export function searchNSEInstruments(query: string): NSEInstrument[] {
  if (!query || !query.trim()) return [...NSE_MASTER_DIRECTORY];
  const q = query.trim().toLowerCase();
  return NSE_MASTER_DIRECTORY.filter(
    (i) =>
      i.ticker.toLowerCase().includes(q) ||
      i.name.toLowerCase().includes(q) ||
      i.sector.toLowerCase().includes(q)
  );
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
