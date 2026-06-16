def momentum(prices, months):

    period = months * 21

    if len(prices) < period:
        return 0

    return (
        prices.iloc[-1] /
        prices.iloc[-period] - 1
    ) * 100
