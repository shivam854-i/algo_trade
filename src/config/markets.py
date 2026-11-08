"""Market Jurisdiction Configuration and Governance Helpers.

Enforces market enablement, canonical normalization, and provides the default
Nifty 50 and Indian equity constituent universes for the Indian equity focus.
Exclusively supports Indian Equities (NSE and BSE) in INR (₹).
"""

from pathlib import Path
from typing import List, Optional
import yaml

# Official, complete 50 constituents of the Nifty 50 index with .NS suffix
NIFTY_50_TICKERS: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "AXISBANK.NS",
    "HINDUNILVR.NS",
    "BAJFINANCE.NS",
    "MARUTI.NS",
    "ASIANPAINT.NS",
    "HCLTECH.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "TATASTEEL.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "ONGC.NS",
    "M&M.NS",
    "JSWSTEEL.NS",
    "COALINDIA.NS",
    "BAJAJFINSV.NS",
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "BPCL.NS",
    "GRASIM.NS",
    "CIPLA.NS",
    "NESTLEIND.NS",
    "WIPRO.NS",
    "TATACONSUM.NS",
    "DRREDDY.NS",
    "EICHERMOT.NS",
    "HEROMOTOCO.NS",
    "DIVISLAB.NS",
    "HINDALCO.NS",
    "APOLLOHOSP.NS",
    "SHRIRAMFIN.NS",
    "TRENT.NS",
    "BEL.NS",
    "BRITANNIA.NS",
    "SBILIFE.NS",
    "HDFCLIFE.NS",
    "TECHM.NS",
    "BAJAJ-AUTO.NS",
    "INDUSINDBK.NS",
]

# Prominent BSE 30 Sensex constituents with .BO suffix
BSE_SENSEX_TICKERS: List[str] = [
    "RELIANCE.BO",
    "TCS.BO",
    "HDFCBANK.BO",
    "INFY.BO",
    "ICICIBANK.BO",
    "SBIN.BO",
    "BHARTIARTL.BO",
    "ITC.BO",
    "KOTAKBANK.BO",
    "LT.BO",
    "AXISBANK.BO",
    "HINDUNILVR.BO",
    "BAJFINANCE.BO",
    "MARUTI.BO",
    "ASIANPAINT.BO",
]

# Prominent Nifty Next 50 Constituents (Large-Cap Growth & Sector Leaders)
NIFTY_NEXT_50_TICKERS: List[str] = [
    "BEL.NS",
    "HAL.NS",
    "TRENT.NS",
    "ZOMATO.NS",
    "JIOFIN.NS",
    "TATAPOWER.NS",
    "POLYCAB.NS",
    "IRFC.NS",
    "CHOLAFIN.NS",
    "PERSISTENT.NS",
    "MAXHEALTH.NS",
    "DIXON.NS",
    "PIDILITIND.NS",
    "VEDL.NS",
    "SIEMENS.NS",
    "ABB.NS",
    "HAVELLS.NS",
    "DLF.NS",
    "GODREJPROP.NS",
    "AMBUJACEM.NS",
    "BANKBARODA.NS",
    "PNB.NS",
    "CANBK.NS",
    "GAIL.NS",
    "IOC.NS",
    "INDIGO.NS",
    "MOTHERSON.NS",
    "BOSCHLTD.NS",
    "LTIM.NS",
    "NAUKRI.NS",
    "BERGEPAINT.NS",
    "MARICO.NS",
    "DABUR.NS",
    "ICICIPRULI.NS",
    "ICICIGI.NS",
    "SBICARD.NS",
    "RECLTD.NS",
    "PFC.NS",
    "TORNTPHARM.NS",
    "ZYDUSLIFE.NS",
    "LUPIN.NS",
    "AUROPHARMA.NS",
    "COLPAL.NS",
    "SRF.NS",
    "UNITDSPR.NS",
    "VBL.NS",
    "TATACOMM.NS",
    "BAJAJHLDNG.NS",
]

# Prominent Nifty Midcap & Smallcap High-Beta / Momentum Instruments
NIFTY_MIDCAP_TICKERS: List[str] = [
    "SUZLON.NS",
    "RVNL.NS",
    "IRCTC.NS",
    "KALYANKJIL.NS",
    "PRESTIGE.NS",
    "OBEROIRLTY.NS",
    "FEDERALBNK.NS",
    "IDFCFIRSTB.NS",
    "AUBANK.NS",
    "ASHOKLEY.NS",
    "BHARATFORG.NS",
    "TATAELXSI.NS",
    "KPITTECH.NS",
    "COFORGE.NS",
    "MPHASIS.NS",
    "DEEPAKNTR.NS",
    "TATACHEM.NS",
    "BIOCON.NS",
    "SUNTV.NS",
    "ZEEL.NS",
    "EXIDEIND.NS",
    "APOLLOTYRE.NS",
    "VOLTAS.NS",
    "BLUESTARCO.NS",
    "ESCORTS.NS",
    "GMRINFRA.NS",
    "NHPC.NS",
    "SJVN.NS",
    "HUDCO.NS",
    "NBCC.NS",
    "MAZDOCK.NS",
    "COCHINSHIP.NS",
]

# Comprehensive NSE Master Directory with Company Name, Sector, Index & Market Cap Tier
NSE_MASTER_CATALOG: List[dict] = [
    # NIFTY 50 Blue Chips
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries Ltd.", "sector": "Energy & Oil/Gas", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services Ltd.", "sector": "Information Technology", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "INFY.NS", "name": "Infosys Ltd.", "sector": "Information Technology", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SBIN.NS", "name": "State Bank of India (SBI)", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd.", "sector": "Telecom", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ITC.NS", "name": "ITC Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro Ltd.", "sector": "Infrastructure", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki India Ltd.", "sector": "Automobiles", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ASIANPAINT.NS", "name": "Asian Paints Ltd.", "sector": "Consumer Tech", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies Ltd.", "sector": "Information Technology", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Industries", "sector": "Pharmaceuticals", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TITAN.NS", "name": "Titan Company Ltd.", "sector": "Consumer Tech", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement Ltd.", "sector": "Infrastructure", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TATASTEEL.NS", "name": "Tata Steel Ltd.", "sector": "Metals & Mining", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "NTPC.NS", "name": "NTPC Ltd.", "sector": "Energy & Power", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "POWERGRID.NS", "name": "Power Grid Corporation of India", "sector": "Energy & Power", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ONGC.NS", "name": "Oil & Natural Gas Corp Ltd.", "sector": "Energy & Oil/Gas", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "M&M.NS", "name": "Mahindra & Mahindra Ltd.", "sector": "Automobiles", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "JSWSTEEL.NS", "name": "JSW Steel Ltd.", "sector": "Metals & Mining", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "COALINDIA.NS", "name": "Coal India Ltd.", "sector": "Energy & Power", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BAJAJFINSV.NS", "name": "Bajaj Finserv Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ADANIENT.NS", "name": "Adani Enterprises Ltd.", "sector": "Infrastructure", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ADANIPORTS.NS", "name": "Adani Ports & SEZ Ltd.", "sector": "Infrastructure", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BPCL.NS", "name": "Bharat Petroleum Corp Ltd.", "sector": "Energy & Oil/Gas", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "GRASIM.NS", "name": "Grasim Industries Ltd.", "sector": "Infrastructure", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "CIPLA.NS", "name": "Cipla Ltd.", "sector": "Pharmaceuticals", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "NESTLEIND.NS", "name": "Nestle India Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "WIPRO.NS", "name": "Wipro Ltd.", "sector": "Information Technology", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TATACONSUM.NS", "name": "Tata Consumer Products Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories", "sector": "Pharmaceuticals", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "EICHERMOT.NS", "name": "Eicher Motors Ltd.", "sector": "Automobiles", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp Ltd.", "sector": "Automobiles", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "DIVISLAB.NS", "name": "Divi's Laboratories Ltd.", "sector": "Pharmaceuticals", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HINDALCO.NS", "name": "Hindalco Industries Ltd.", "sector": "Metals & Mining", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals Enterprise", "sector": "Pharmaceuticals", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SHRIRAMFIN.NS", "name": "Shriram Finance Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TRENT.NS", "name": "Trent Ltd.", "sector": "Consumer Tech", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BEL.NS", "name": "Bharat Electronics Ltd.", "sector": "Defense & Aerospace", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BRITANNIA.NS", "name": "Britannia Industries Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SBILIFE.NS", "name": "SBI Life Insurance Co Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HDFCLIFE.NS", "name": "HDFC Life Insurance Co Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TECHM.NS", "name": "Tech Mahindra Ltd.", "sector": "Information Technology", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BAJAJ-AUTO.NS", "name": "Bajaj Auto Ltd.", "sector": "Automobiles", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "INDUSINDBK.NS", "name": "IndusInd Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    # NIFTY NEXT 50 High Growth & Leaders
    {"ticker": "HAL.NS", "name": "Hindustan Aeronautics Ltd.", "sector": "Defense & Aerospace", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ZOMATO.NS", "name": "Zomato Ltd.", "sector": "Consumer Tech", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "JIOFIN.NS", "name": "Jio Financial Services Ltd.", "sector": "Banking & Finance", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TATAPOWER.NS", "name": "Tata Power Company Ltd.", "sector": "Energy & Power", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "POLYCAB.NS", "name": "Polycab India Ltd.", "sector": "Infrastructure", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "IRFC.NS", "name": "Indian Railway Finance Corp", "sector": "Railways", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "CHOLAFIN.NS", "name": "Cholamandalam Investment & Fin", "sector": "Banking & Finance", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "PERSISTENT.NS", "name": "Persistent Systems Ltd.", "sector": "Information Technology", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "MAXHEALTH.NS", "name": "Max Healthcare Institute", "sector": "Pharmaceuticals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "DIXON.NS", "name": "Dixon Technologies India", "sector": "Consumer Tech", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "PIDILITIND.NS", "name": "Pidilite Industries Ltd.", "sector": "Chemicals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "VEDL.NS", "name": "Vedanta Ltd.", "sector": "Metals & Mining", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SIEMENS.NS", "name": "Siemens India Ltd.", "sector": "Infrastructure", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ABB.NS", "name": "ABB India Ltd.", "sector": "Infrastructure", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "HAVELLS.NS", "name": "Havells India Ltd.", "sector": "Consumer Tech", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "DLF.NS", "name": "DLF Ltd.", "sector": "Realty", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "GODREJPROP.NS", "name": "Godrej Properties Ltd.", "sector": "Realty", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "AMBUJACEM.NS", "name": "Ambuja Cements Ltd.", "sector": "Infrastructure", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "BANKBARODA.NS", "name": "Bank of Baroda", "sector": "Banking & Finance", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "PNB.NS", "name": "Punjab National Bank", "sector": "Banking & Finance", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "CANBK.NS", "name": "Canara Bank", "sector": "Banking & Finance", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "GAIL.NS", "name": "GAIL (India) Ltd.", "sector": "Energy & Oil/Gas", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "IOC.NS", "name": "Indian Oil Corporation", "sector": "Energy & Oil/Gas", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "INDIGO.NS", "name": "InterGlobe Aviation (IndiGo)", "sector": "Infrastructure", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "MOTHERSON.NS", "name": "Samvardhana Motherson Int.", "sector": "Automobiles", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "LTIM.NS", "name": "LTIMindtree Ltd.", "sector": "Information Technology", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "NAUKRI.NS", "name": "Info Edge (India) Ltd.", "sector": "Consumer Tech", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "MARICO.NS", "name": "Marico Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "DABUR.NS", "name": "Dabur India Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "TORNTPHARM.NS", "name": "Torrent Pharmaceuticals", "sector": "Pharmaceuticals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "ZYDUSLIFE.NS", "name": "Zydus Lifesciences Ltd.", "sector": "Pharmaceuticals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "LUPIN.NS", "name": "Lupin Ltd.", "sector": "Pharmaceuticals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "VBL.NS", "name": "Varun Beverages Ltd.", "sector": "Fast Moving Consumer Goods", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    {"ticker": "SRF.NS", "name": "SRF Ltd.", "sector": "Chemicals", "index": "NIFTY_NEXT_50", "market_cap_tier": "Large Cap", "exchange": "NSE"},
    # NIFTY Midcap & Smallcap Momentum Stocks
    {"ticker": "SUZLON.NS", "name": "Suzlon Energy Ltd.", "sector": "Energy & Power", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "RVNL.NS", "name": "Rail Vikas Nigam Ltd.", "sector": "Railways", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "IRCTC.NS", "name": "Indian Railway Catering & Tour", "sector": "Railways", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "MAZDOCK.NS", "name": "Mazagon Dock Shipbuilders", "sector": "Defense & Aerospace", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "COCHINSHIP.NS", "name": "Cochin Shipyard Ltd.", "sector": "Defense & Aerospace", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "FEDERALBNK.NS", "name": "The Federal Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "IDFCFIRSTB.NS", "name": "IDFC First Bank Ltd.", "sector": "Banking & Finance", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "AUBANK.NS", "name": "AU Small Finance Bank", "sector": "Banking & Finance", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "ASHOKLEY.NS", "name": "Ashok Leyland Ltd.", "sector": "Automobiles", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "BHARATFORG.NS", "name": "Bharat Forge Ltd.", "sector": "Automobiles", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "TATAELXSI.NS", "name": "Tata Elxsi Ltd.", "sector": "Information Technology", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "KPITTECH.NS", "name": "KPIT Technologies Ltd.", "sector": "Information Technology", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "COFORGE.NS", "name": "Coforge Ltd.", "sector": "Information Technology", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "MPHASIS.NS", "name": "Mphasis Ltd.", "sector": "Information Technology", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "DEEPAKNTR.NS", "name": "Deepak Nitrite Ltd.", "sector": "Chemicals", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "TATACHEM.NS", "name": "Tata Chemicals Ltd.", "sector": "Chemicals", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "BIOCON.NS", "name": "Biocon Ltd.", "sector": "Pharmaceuticals", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "VOLTAS.NS", "name": "Voltas Ltd.", "sector": "Consumer Tech", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "PRESTIGE.NS", "name": "Prestige Estates Projects", "sector": "Realty", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "OBEROIRLTY.NS", "name": "Oberoi Realty Ltd.", "sector": "Realty", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
    {"ticker": "NHPC.NS", "name": "NHPC Ltd.", "sector": "Energy & Power", "index": "NIFTY_MIDCAP", "market_cap_tier": "Mid Cap", "exchange": "NSE"},
]

# Quick mapping of Ticker to Sector
NSE_SECTOR_MAP: dict = {item["ticker"]: item["sector"] for item in NSE_MASTER_CATALOG}


# Canonical Indian market benchmarks
INDIAN_BENCHMARKS: List[str] = [
    "^NSEI",       # Nifty 50
    "^BSESN",      # BSE Sensex
    "^NSEBANK",    # Nifty Bank
]


def normalize_market(market_str: str) -> str:
    """Normalizes market identifier strings into canonical form.

    Maps INDIAN_NSE, NSE, NSE_CASH, and INDIA equivalently to NSE_CASH.
    Maps INDIAN_BSE, BSE, BSE_CASH to BSE_CASH.
    Maps US, US_EQUITIES, NYSE, NASDAQ to US_EQUITIES.
    Maps CRYPTO, CRYPTOCURRENCY to CRYPTO.
    Maps COMMODITY, COMMODITIES, CME to COMMODITIES.
    Maps FOREX, FX to FOREX.
    """
    if not market_str or not isinstance(market_str, str):
        return ""
    norm = market_str.strip().upper()
    if norm in ("INDIAN_NSE", "NSE", "NSE_CASH", "INDIA", "INDIAN_EQUITIES", "EQUITIES"):
        return "NSE_CASH"
    if norm in ("INDIAN_BSE", "BSE", "BSE_CASH"):
        return "BSE_CASH"
    if norm in ("US", "US_EQUITIES", "NYSE", "NASDAQ"):
        return "US_EQUITIES"
    if norm in ("CRYPTO", "CRYPTOCURRENCY"):
        return "CRYPTO"
    if norm in ("COMMODITY", "COMMODITIES", "CME"):
        return "COMMODITIES"
    if norm in ("FOREX", "FX"):
        return "FOREX"
    return norm


def get_market_for_ticker(ticker: str) -> str:
    """Infers canonical market jurisdiction from ticker symbol pattern."""
    if not ticker or not isinstance(ticker, str):
        return "US_EQUITIES"
    tk = ticker.strip().upper()
    if tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS")):
        return "NSE_CASH"
    if tk.endswith("=F") or tk in ("GLD", "SLV", "USO", "UNG"):
        return "COMMODITIES"
    if tk.endswith("=X") or tk in ("DX-Y.NYB", "UUP"):
        return "FOREX"
    if "-USD" in tk or "-USDT" in tk or tk in ("BTC", "ETH", "SOL", "DOGE", "XRP"):
        return "CRYPTO"
    return "US_EQUITIES"


def get_enabled_markets() -> List[str]:
    """Reads enabled markets from config/config.yaml or falls back to ['NSE_CASH']."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "enabled_markets" in data:
                    return [normalize_market(m) for m in data["enabled_markets"] if m]
        except Exception:
            pass
    return ["NSE_CASH"]


def is_market_enabled(market_str: str) -> bool:
    """Checks whether the given market (or ticker market) is currently enabled."""
    norm = normalize_market(market_str)
    enabled = get_enabled_markets()
    return norm in enabled


def validate_market_enabled(market_str: str) -> None:
    """Validates that a market is enabled; raises ValueError if disabled."""
    norm = normalize_market(market_str)
    enabled = get_enabled_markets()
    if norm not in enabled:
        raise ValueError(
            f"Market '{market_str}' is disabled. Only enabled markets: {enabled}"
        )


def get_default_universe() -> List[str]:
    """Returns the default asset universe (Nifty 50 constituents)."""
    return list(NIFTY_50_TICKERS)

