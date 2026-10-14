"""Synthetic supply-chain networks, disruptions and the surrogate training dataset.

    profiles     industry profiles, Indian city catalogue, transport-mode variability, seasonality, bullwhip
    networks     seeded network generator (7 archetypes x 6 industries, 10-60 nodes) -> engine graphs
    disruptions  seeded disruption library (13 types incl. weather-driven and compound events) -> core events
    build        dataset builder CLI: exact simulator per network x disruption -> parquet + data card
    demos        the three ready-made demo networks (FMCG, pharma cold-chain, electronics)

Every assumption is documented in data/synth_assumptions.md.
"""
