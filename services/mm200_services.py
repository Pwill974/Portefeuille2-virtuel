def mm200_signal(close, mm200):

    if close > mm200 * 1.03:
        return "ACHAT"

    elif close > mm200:
        return "SURVEILLANCE"

    return "VENTE"
