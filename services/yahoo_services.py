import yfinance as yf

def get_price(ticker):

    data = yf.Ticker(ticker)

    return data.history(period="5d")["Close"].iloc[-1]

def get_history(ticker):

    data = yf.Ticker(ticker)

    return data.history(period="3y")
