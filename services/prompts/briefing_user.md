Generate today's market briefing for the sample slate.
Use tools to inspect games and lines, detect stale last_updated outliers and off-market prices vs other books, compute vig and implieds where helpful, use best_line_for_market where useful for value angles, call scan_cross_book_arbitrage (whole slate or per game) to report any cross-book arbitrage-style edges, and rank sportsbooks by how tight/reasonable their prices look on this slate.
Every anomaly and value_opportunity row must include confidence + confidence_basis tied to tool evidence. Optionally add market_overview_confidence fields and per-book confidence on rankings.
End with the JSON object specified in your instructions.
