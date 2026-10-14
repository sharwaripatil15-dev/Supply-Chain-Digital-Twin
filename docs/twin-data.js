// Generated from the real AEGIS engine (core.sim, core.chaos, core.strategies) on backend/mock/sample_*.csv
window.AEGIS_DATA = {
 "nodes": [
  {
   "id": "S1",
   "name": "Pune Steel Coils",
   "kind": "supplier",
   "city": "Pune",
   "lat": "18.52",
   "lon": "73.86",
   "capacity": "900",
   "stock": "2200",
   "demand": "0",
   "reliability": "0.891",
   "utilization": "0.72",
   "risk": "0.31",
   "backup": "False"
  },
  {
   "id": "S2",
   "name": "Chennai Electronics",
   "kind": "supplier",
   "city": "Chennai",
   "lat": "13.08",
   "lon": "80.27",
   "capacity": "800",
   "stock": "1200",
   "demand": "0",
   "reliability": "0.748",
   "utilization": "0.84",
   "risk": "0.72",
   "backup": "False"
  },
  {
   "id": "S3",
   "name": "Gujarat Polymers",
   "kind": "supplier",
   "city": "Ahmedabad",
   "lat": "23.02",
   "lon": "72.57",
   "capacity": "700",
   "stock": "1500",
   "demand": "0",
   "reliability": "0.867",
   "utilization": "0.66",
   "risk": "0.38",
   "backup": "False"
  },
  {
   "id": "S4",
   "name": "Kolkata Backup Components",
   "kind": "supplier",
   "city": "Kolkata",
   "lat": "22.57",
   "lon": "88.36",
   "capacity": "400",
   "stock": "900",
   "demand": "0",
   "reliability": "0.905",
   "utilization": "0.35",
   "risk": "0.27",
   "backup": "True"
  },
  {
   "id": "F1",
   "name": "Bengaluru Assembly",
   "kind": "factory",
   "city": "Bengaluru",
   "lat": "12.97",
   "lon": "77.59",
   "capacity": "1000",
   "stock": "1400",
   "demand": "0",
   "reliability": "0.846",
   "utilization": "0.88",
   "risk": "0.44",
   "backup": "False"
  },
  {
   "id": "F2",
   "name": "Hyderabad Plant",
   "kind": "factory",
   "city": "Hyderabad",
   "lat": "17.39",
   "lon": "78.49",
   "capacity": "800",
   "stock": "1100",
   "demand": "0",
   "reliability": "0.878",
   "utilization": "0.79",
   "risk": "0.35",
   "backup": "False"
  },
  {
   "id": "F3",
   "name": "Nashik Works",
   "kind": "factory",
   "city": "Nashik",
   "lat": "19.99",
   "lon": "73.79",
   "capacity": "600",
   "stock": "800",
   "demand": "0",
   "reliability": "0.898",
   "utilization": "0.71",
   "risk": "0.29",
   "backup": "False"
  },
  {
   "id": "W1",
   "name": "Bhiwandi DC",
   "kind": "warehouse",
   "city": "Mumbai",
   "lat": "19.3",
   "lon": "73.06",
   "capacity": "900",
   "stock": "1800",
   "demand": "0",
   "reliability": "0.885",
   "utilization": "0.74",
   "risk": "0.33",
   "backup": "False"
  },
  {
   "id": "W2",
   "name": "Gurugram DC",
   "kind": "warehouse",
   "city": "Delhi",
   "lat": "28.46",
   "lon": "77.03",
   "capacity": "800",
   "stock": "1600",
   "demand": "0",
   "reliability": "0.909",
   "utilization": "0.62",
   "risk": "0.26",
   "backup": "False"
  },
  {
   "id": "W3",
   "name": "Sriperumbudur DC",
   "kind": "warehouse",
   "city": "Chennai",
   "lat": "12.97",
   "lon": "79.95",
   "capacity": "600",
   "stock": "700",
   "demand": "0",
   "reliability": "0.797",
   "utilization": "0.86",
   "risk": "0.58",
   "backup": "False"
  },
  {
   "id": "W4",
   "name": "Nagpur Hub",
   "kind": "warehouse",
   "city": "Nagpur",
   "lat": "21.15",
   "lon": "79.09",
   "capacity": "700",
   "stock": "1300",
   "demand": "0",
   "reliability": "0.857",
   "utilization": "0.81",
   "risk": "0.41",
   "backup": "False"
  },
  {
   "id": "C1",
   "name": "Mumbai Retail",
   "kind": "customer",
   "city": "Mumbai",
   "lat": "19.08",
   "lon": "72.88",
   "capacity": "0",
   "stock": "600",
   "demand": "300",
   "reliability": "0.923",
   "utilization": "0.0",
   "risk": "0.22",
   "backup": "False"
  },
  {
   "id": "C2",
   "name": "Delhi Retail",
   "kind": "customer",
   "city": "Delhi",
   "lat": "28.7",
   "lon": "77.1",
   "capacity": "0",
   "stock": "560",
   "demand": "280",
   "reliability": "0.912",
   "utilization": "0.0",
   "risk": "0.25",
   "backup": "False"
  },
  {
   "id": "C3",
   "name": "Bengaluru Retail",
   "kind": "customer",
   "city": "Bengaluru",
   "lat": "12.93",
   "lon": "77.62",
   "capacity": "0",
   "stock": "440",
   "demand": "220",
   "reliability": "0.786",
   "utilization": "0.0",
   "risk": "0.61",
   "backup": "False"
  },
  {
   "id": "C4",
   "name": "Hyderabad Retail",
   "kind": "customer",
   "city": "Hyderabad",
   "lat": "17.44",
   "lon": "78.38",
   "capacity": "0",
   "stock": "360",
   "demand": "180",
   "reliability": "0.864",
   "utilization": "0.0",
   "risk": "0.39",
   "backup": "False"
  },
  {
   "id": "C5",
   "name": "Jaipur Retail",
   "kind": "customer",
   "city": "Jaipur",
   "lat": "26.91",
   "lon": "75.79",
   "capacity": "0",
   "stock": "300",
   "demand": "150",
   "reliability": "0.916",
   "utilization": "0.0",
   "risk": "0.24",
   "backup": "False"
  }
 ],
 "edges": [
  {
   "source": "S1",
   "target": "F1",
   "capacity": "500",
   "lead": "2",
   "cost": "42",
   "co2": "3.1"
  },
  {
   "source": "S1",
   "target": "F3",
   "capacity": "450",
   "lead": "1",
   "cost": "18",
   "co2": "1.2"
  },
  {
   "source": "S2",
   "target": "F1",
   "capacity": "600",
   "lead": "1",
   "cost": "22",
   "co2": "1.5"
  },
  {
   "source": "S2",
   "target": "F2",
   "capacity": "400",
   "lead": "2",
   "cost": "35",
   "co2": "2.4"
  },
  {
   "source": "S3",
   "target": "F3",
   "capacity": "400",
   "lead": "2",
   "cost": "30",
   "co2": "2.2"
  },
  {
   "source": "S3",
   "target": "F2",
   "capacity": "300",
   "lead": "3",
   "cost": "48",
   "co2": "3.6"
  },
  {
   "source": "S4",
   "target": "F1",
   "capacity": "250",
   "lead": "4",
   "cost": "85",
   "co2": "6.8"
  },
  {
   "source": "S4",
   "target": "F2",
   "capacity": "250",
   "lead": "3",
   "cost": "70",
   "co2": "5.4"
  },
  {
   "source": "F1",
   "target": "W3",
   "capacity": "550",
   "lead": "1",
   "cost": "14",
   "co2": "0.9"
  },
  {
   "source": "F1",
   "target": "W4",
   "capacity": "350",
   "lead": "2",
   "cost": "38",
   "co2": "2.7"
  },
  {
   "source": "F2",
   "target": "W4",
   "capacity": "400",
   "lead": "1",
   "cost": "20",
   "co2": "1.4"
  },
  {
   "source": "F2",
   "target": "W2",
   "capacity": "350",
   "lead": "3",
   "cost": "55",
   "co2": "4.1"
  },
  {
   "source": "F3",
   "target": "W1",
   "capacity": "450",
   "lead": "1",
   "cost": "12",
   "co2": "0.8"
  },
  {
   "source": "F3",
   "target": "W2",
   "capacity": "200",
   "lead": "3",
   "cost": "50",
   "co2": "3.9"
  },
  {
   "source": "W1",
   "target": "C1",
   "capacity": "400",
   "lead": "1",
   "cost": "8",
   "co2": "0.4"
  },
  {
   "source": "W1",
   "target": "C5",
   "capacity": "150",
   "lead": "2",
   "cost": "32",
   "co2": "2.3"
  },
  {
   "source": "W2",
   "target": "C2",
   "capacity": "350",
   "lead": "1",
   "cost": "9",
   "co2": "0.5"
  },
  {
   "source": "W2",
   "target": "C5",
   "capacity": "200",
   "lead": "1",
   "cost": "15",
   "co2": "1.0"
  },
  {
   "source": "W3",
   "target": "C3",
   "capacity": "350",
   "lead": "1",
   "cost": "10",
   "co2": "0.6"
  },
  {
   "source": "W3",
   "target": "C4",
   "capacity": "150",
   "lead": "2",
   "cost": "26",
   "co2": "1.8"
  },
  {
   "source": "W4",
   "target": "C4",
   "capacity": "250",
   "lead": "1",
   "cost": "12",
   "co2": "0.8"
  },
  {
   "source": "W4",
   "target": "C2",
   "capacity": "200",
   "lead": "2",
   "cost": "34",
   "co2": "2.6"
  },
  {
   "source": "W4",
   "target": "C1",
   "capacity": "120",
   "lead": "2",
   "cost": "36",
   "co2": "2.7"
  }
 ],
 "scenarios": [
  {
   "id": "f1",
   "title": "Bengaluru Assembly (F1) shuts for 10 days",
   "events": [
    {
     "type": "node",
     "target": "F1",
     "start": 0,
     "duration": 10,
     "severity": 1.0
    }
   ],
   "timeline": [
    {
     "day": 0,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "stressed",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 1,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "stressed",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 2,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 3,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 4,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 5,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 6,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 7,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 8,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 9,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 10,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 11,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 12,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 13,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    }
   ],
   "total_unmet": 1760.0,
   "survival_clock_days": 2,
   "revenue_at_risk": 7392000.0,
   "stockout_day": {
    "C3": 2
   },
   "log": [
    "Day 0: EVENT outage at F1 for 10d (severity 1.00)",
    "Day 0: S2 Chennai Electronics (Chennai) stressed - output cut, downstream lanes blocked (throughput -37%)",
    "Day 0: F1 Bengaluru Assembly (Bengaluru) DOWN",
    "Day 0: W3 Sriperumbudur DC (Chennai) stressed - inbound supply short (throughput -100%)",
    "Day 0: C3 Bengaluru Retail (Bengaluru) stressed - short 220 units, drawing down stock (220 left)",
    "Day 2: C3 Bengaluru Retail (Bengaluru) STOCKOUT",
    "Day 3: F3 Nashik Works (Nashik) stressed - running at 100% of capacity",
    "Day 10: EVENT ended at F1",
    "Day 10: S2 Chennai Electronics (Chennai) recovered",
    "Day 10: F1 Bengaluru Assembly (Bengaluru) recovered",
    "Day 10: F3 Nashik Works (Nashik) recovered",
    "Day 10: W3 Sriperumbudur DC (Chennai) recovered"
   ],
   "strategies": [
    {
     "name": "Do nothing",
     "cost": 25344.0,
     "unmet": 2900.0,
     "recovery_days": 10,
     "co2": 33.11,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute only",
     "cost": 36840.0,
     "unmet": 1760.0,
     "recovery_days": 10,
     "co2": 40.01,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute + backup",
     "cost": 36840.0,
     "unmet": 1760.0,
     "recovery_days": 10,
     "co2": 40.01,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Inventory buffer",
     "cost": 47500.0,
     "unmet": 1950.0,
     "recovery_days": 10,
     "co2": 35.58,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Production shift",
     "cost": 36840.0,
     "unmet": 1760.0,
     "recovery_days": 10,
     "co2": 40.01,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Full plan",
     "cost": 47500.0,
     "unmet": 810.0,
     "recovery_days": 10,
     "co2": 42.48,
     "recommended": true,
     "safe": true
    },
    {
     "name": "Green plan",
     "cost": 47500.0,
     "unmet": 810.0,
     "recovery_days": 10,
     "co2": 35.55,
     "recommended": false,
     "safe": true
    }
   ]
  },
  {
   "id": "w3",
   "title": "Flood closes Sriperumbudur DC (W3) for 7 days",
   "events": [
    {
     "type": "node",
     "target": "W3",
     "start": 0,
     "duration": 7,
     "severity": 1.0
    }
   ],
   "timeline": [
    {
     "day": 0,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "stressed",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 1,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "stressed",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 2,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 3,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 4,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 5,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 6,
     "unmet": 220,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "down",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "down",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 7,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 8,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 9,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 10,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 11,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 12,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 13,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    }
   ],
   "total_unmet": 1100.0,
   "survival_clock_days": 2,
   "revenue_at_risk": 4620000.0,
   "stockout_day": {
    "C3": 2
   },
   "log": [
    "Day 0: EVENT outage at W3 for 7d (severity 1.00)",
    "Day 0: S2 Chennai Electronics (Chennai) stressed - output cut, downstream lanes blocked (throughput -48%)",
    "Day 0: F1 Bengaluru Assembly (Bengaluru) stressed - inbound supply short (throughput -100%)",
    "Day 0: F3 Nashik Works (Nashik) stressed - running at 100% of capacity",
    "Day 0: W3 Sriperumbudur DC (Chennai) DOWN",
    "Day 0: C3 Bengaluru Retail (Bengaluru) stressed - short 220 units, drawing down stock (220 left)",
    "Day 2: C3 Bengaluru Retail (Bengaluru) STOCKOUT",
    "Day 7: EVENT ended at W3",
    "Day 7: S2 Chennai Electronics (Chennai) recovered",
    "Day 7: F1 Bengaluru Assembly (Bengaluru) recovered",
    "Day 7: F3 Nashik Works (Nashik) recovered",
    "Day 7: W3 Sriperumbudur DC (Chennai) recovered"
   ],
   "strategies": [
    {
     "name": "Do nothing",
     "cost": 17741.0,
     "unmet": 1790.0,
     "recovery_days": 7,
     "co2": 23.18,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute only",
     "cost": 25788.0,
     "unmet": 1100.0,
     "recovery_days": 7,
     "co2": 28.01,
     "recommended": true,
     "safe": true
    },
    {
     "name": "Reroute + backup",
     "cost": 25788.0,
     "unmet": 1100.0,
     "recovery_days": 7,
     "co2": 28.01,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Inventory buffer",
     "cost": 75075.0,
     "unmet": 1790.0,
     "recovery_days": 7,
     "co2": 18.92,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Production shift",
     "cost": 25788.0,
     "unmet": 1100.0,
     "recovery_days": 7,
     "co2": 28.01,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Full plan",
     "cost": 75075.0,
     "unmet": 1100.0,
     "recovery_days": 7,
     "co2": 21.57,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Green plan",
     "cost": 75075.0,
     "unmet": 1100.0,
     "recovery_days": 7,
     "co2": 15.46,
     "recommended": false,
     "safe": true
    }
   ]
  },
  {
   "id": "pair",
   "title": "Hidden pair: F1 and F2 both down for 10 days",
   "events": [
    {
     "type": "node",
     "target": "F1",
     "start": 0,
     "duration": 10,
     "severity": 1.0
    },
    {
     "type": "node",
     "target": "F2",
     "start": 0,
     "duration": 10,
     "severity": 1.0
    }
   ],
   "timeline": [
    {
     "day": 0,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "stressed",
      "C3": "stressed",
      "C4": "stressed",
      "C5": "ok"
     }
    },
    {
     "day": 1,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "stressed",
      "C3": "stressed",
      "C4": "stressed",
      "C5": "ok"
     }
    },
    {
     "day": 2,
     "unmet": 400,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "stressed",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 3,
     "unmet": 400,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "stressed",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 4,
     "unmet": 490,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 5,
     "unmet": 530,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 6,
     "unmet": 530,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 7,
     "unmet": 530,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 8,
     "unmet": 530,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 9,
     "unmet": 530,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "down",
      "F2": "down",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "stressed",
      "C1": "ok",
      "C2": "down",
      "C3": "down",
      "C4": "down",
      "C5": "ok"
     }
    },
    {
     "day": 10,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 11,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 12,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 13,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    }
   ],
   "total_unmet": 3940.0,
   "survival_clock_days": 2,
   "revenue_at_risk": 16548000.0,
   "stockout_day": {
    "C3": 2,
    "C4": 2,
    "C2": 4
   },
   "log": [
    "Day 0: EVENT outage at F1 for 10d (severity 1.00)",
    "Day 0: EVENT outage at F2 for 10d (severity 1.00)",
    "Day 0: S2 Chennai Electronics (Chennai) stressed - output cut, downstream lanes blocked (throughput -100%)",
    "Day 0: F1 Bengaluru Assembly (Bengaluru) DOWN",
    "Day 0: F2 Hyderabad Plant (Hyderabad) DOWN",
    "Day 0: F3 Nashik Works (Nashik) stressed - running at 100% of capacity",
    "Day 0: W3 Sriperumbudur DC (Chennai) stressed - inbound supply short (throughput -100%)",
    "Day 0: W4 Nagpur Hub (Nagpur) stressed - inbound supply short (throughput -100%)",
    "Day 0: C2 Delhi Retail (Delhi) stressed - short 130 units, drawing down stock (430 left)",
    "Day 0: C3 Bengaluru Retail (Bengaluru) stressed - short 220 units, drawing down stock (220 left)",
    "Day 0: C4 Hyderabad Retail (Hyderabad) stressed - short 180 units, drawing down stock (180 left)",
    "Day 2: C3 Bengaluru Retail (Bengaluru) STOCKOUT"
   ],
   "strategies": [
    {
     "name": "Do nothing",
     "cost": 0.0,
     "unmet": 4640.0,
     "recovery_days": 10,
     "co2": 18.93,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute only",
     "cost": 0.0,
     "unmet": 3440.0,
     "recovery_days": 10,
     "co2": 24.58,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute + backup",
     "cost": 0.0,
     "unmet": 3440.0,
     "recovery_days": 10,
     "co2": 24.58,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Inventory buffer",
     "cost": 20000.0,
     "unmet": 4240.0,
     "recovery_days": 10,
     "co2": 19.97,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Production shift",
     "cost": 10000.0,
     "unmet": 3440.0,
     "recovery_days": 10,
     "co2": 26.85,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Full plan",
     "cost": 30000.0,
     "unmet": 3040.0,
     "recovery_days": 10,
     "co2": 27.87,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Green plan",
     "cost": 20000.0,
     "unmet": 3040.0,
     "recovery_days": 10,
     "co2": 24.24,
     "recommended": true,
     "safe": true
    }
   ]
  },
  {
   "id": "spike",
   "title": "Festival spike: Delhi + Jaipur demand +80% for 7 days",
   "events": [
    {
     "type": "demand",
     "target": "C2",
     "start": 1,
     "duration": 7,
     "severity": 0.8
    },
    {
     "type": "demand",
     "target": "C5",
     "start": 1,
     "duration": 7,
     "severity": 0.8
    }
   ],
   "timeline": [
    {
     "day": 0,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 1,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 2,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 3,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 4,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 5,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 6,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 7,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "stressed",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 8,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 9,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 10,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 11,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 12,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 13,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    }
   ],
   "total_unmet": 0.0,
   "survival_clock_days": 14,
   "revenue_at_risk": 0.0,
   "stockout_day": {},
   "log": [
    "Day 1: EVENT demand spike at C2 for 7d (severity 0.80)",
    "Day 1: EVENT demand spike at C5 for 7d (severity 0.80)",
    "Day 1: S2 Chennai Electronics (Chennai) stressed - running at 100% of capacity",
    "Day 1: F3 Nashik Works (Nashik) stressed - running at 100% of capacity",
    "Day 8: EVENT ended at C2",
    "Day 8: EVENT ended at C5",
    "Day 8: S2 Chennai Electronics (Chennai) recovered",
    "Day 8: F3 Nashik Works (Nashik) recovered"
   ],
   "strategies": [
    {
     "name": "Do nothing",
     "cost": 0.0,
     "unmet": 1598.9,
     "recovery_days": 7,
     "co2": 32.21,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute only",
     "cost": 105278.0,
     "unmet": 0.0,
     "recovery_days": 6,
     "co2": 50.28,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute + backup",
     "cost": 105278.0,
     "unmet": 0.0,
     "recovery_days": 6,
     "co2": 50.28,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Inventory buffer",
     "cost": 75075.0,
     "unmet": 1598.9,
     "recovery_days": 7,
     "co2": 27.95,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Production shift",
     "cost": 104407.0,
     "unmet": 0.0,
     "recovery_days": 6,
     "co2": 49.81,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Full plan",
     "cost": 75075.0,
     "unmet": 0.0,
     "recovery_days": 6,
     "co2": 42.24,
     "recommended": true,
     "safe": true
    },
    {
     "name": "Green plan",
     "cost": 75075.0,
     "unmet": 0.0,
     "recovery_days": 7,
     "co2": 32.89,
     "recommended": false,
     "safe": true
    }
   ]
  },
  {
   "id": "s2",
   "title": "Chennai Electronics (S2) fails for 10 days",
   "events": [
    {
     "type": "node",
     "target": "S2",
     "start": 0,
     "duration": 10,
     "severity": 1.0
    }
   ],
   "timeline": [
    {
     "day": 0,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 1,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 2,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 3,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 4,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 5,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 6,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 7,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 8,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 9,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "down",
      "S3": "ok",
      "S4": "ok",
      "F1": "stressed",
      "F2": "ok",
      "F3": "stressed",
      "W1": "ok",
      "W2": "ok",
      "W3": "stressed",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 10,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 11,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 12,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    },
    {
     "day": 13,
     "unmet": 0,
     "status": {
      "S1": "ok",
      "S2": "ok",
      "S3": "ok",
      "S4": "ok",
      "F1": "ok",
      "F2": "ok",
      "F3": "ok",
      "W1": "ok",
      "W2": "ok",
      "W3": "ok",
      "W4": "ok",
      "C1": "ok",
      "C2": "ok",
      "C3": "ok",
      "C4": "ok",
      "C5": "ok"
     }
    }
   ],
   "total_unmet": 0.0,
   "survival_clock_days": 14,
   "revenue_at_risk": 0.0,
   "stockout_day": {},
   "log": [
    "Day 0: EVENT outage at S2 for 10d (severity 1.00)",
    "Day 0: S2 Chennai Electronics (Chennai) DOWN",
    "Day 0: F1 Bengaluru Assembly (Bengaluru) stressed - inbound supply short (throughput -38%)",
    "Day 0: F3 Nashik Works (Nashik) stressed - running at 100% of capacity",
    "Day 0: W3 Sriperumbudur DC (Chennai) stressed - inbound supply short (throughput -38%)",
    "Day 10: EVENT ended at S2",
    "Day 10: S2 Chennai Electronics (Chennai) recovered",
    "Day 10: F1 Bengaluru Assembly (Bengaluru) recovered",
    "Day 10: F3 Nashik Works (Nashik) recovered",
    "Day 10: W3 Sriperumbudur DC (Chennai) recovered"
   ],
   "strategies": [
    {
     "name": "Do nothing",
     "cost": 0.0,
     "unmet": 4640.0,
     "recovery_days": 10,
     "co2": 18.93,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute only",
     "cost": 92000.0,
     "unmet": 0.0,
     "recovery_days": 0,
     "co2": 53.99,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Reroute + backup",
     "cost": 92000.0,
     "unmet": 0.0,
     "recovery_days": 0,
     "co2": 53.99,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Inventory buffer",
     "cost": 82500.0,
     "unmet": 2990.0,
     "recovery_days": 10,
     "co2": 23.58,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Production shift",
     "cost": 92000.0,
     "unmet": 0.0,
     "recovery_days": 0,
     "co2": 53.99,
     "recommended": false,
     "safe": true
    },
    {
     "name": "Full plan",
     "cost": 82500.0,
     "unmet": 0.0,
     "recovery_days": 0,
     "co2": 45.98,
     "recommended": true,
     "safe": true
    },
    {
     "name": "Green plan",
     "cost": 82500.0,
     "unmet": 0.0,
     "recovery_days": 10,
     "co2": 35.43,
     "recommended": false,
     "safe": true
    }
   ]
  }
 ],
 "chaos": {
  "spof": [
   {
    "target": "F1",
    "unmet": 2200.0
   },
   {
    "target": "W3",
    "unmet": 2200.0
   },
   {
    "target": "F1->W3",
    "unmet": 2200.0
   },
   {
    "target": "W3->C3",
    "unmet": 2200.0
   },
   {
    "target": "F3",
    "unmet": 1800.0
   }
  ],
  "hidden_pairs": [
   {
    "pair": [
     "F1",
     "F2"
    ],
    "unmet": 5300.0,
    "synergy": 3100.0
   },
   {
    "pair": [
     "F2",
     "F3"
    ],
    "unmet": 4100.0,
    "synergy": 2300.0
   },
   {
    "pair": [
     "F3",
     "F2->W2"
    ],
    "unmet": 4100.0,
    "synergy": 2300.0
   },
   {
    "pair": [
     "F3",
     "W4"
    ],
    "unmet": 4100.0,
    "synergy": 2000.0
   },
   {
    "pair": [
     "W2",
     "W4"
    ],
    "unmet": 3100.0,
    "synergy": 2000.0
   }
  ],
  "resilience_score": 61.6
 }
};
