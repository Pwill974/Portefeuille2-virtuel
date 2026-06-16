def alpha_score(
 m3,
 m6,
 m12,
 above_mm200
):

    score = (
        m3 * 0.20 +
        m6 * 0.35 +
        m12 * 0.35
    )

    if above_mm200:
        score += 10

    return round(score, 2)
