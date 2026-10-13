"""Weather- and disaster-aware route risk: providers -> route sampling -> scoring -> impact mapping -> re-routing.

Weather risk is converted into ordinary disruption events (schemas.Event, tagged source="weather"), so the simulator,
Chaos Finder and optimizer run unchanged on it.
"""
