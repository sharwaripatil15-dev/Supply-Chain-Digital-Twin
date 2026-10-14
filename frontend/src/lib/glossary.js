/**
 * One canonical, plain-language definition per metric. Every place a metric is shown uses <Term id=...> so the
 * tooltip text is identical across pages.
 */
export const GLOSSARY = {
  health: { label: 'Health Score', text: 'Overall supply chain health from 0 to 100: resilience 30%, capacity headroom 20%, inventory health 20%, supplier concentration 15%, lead-time risk 15%. Simulated.' },
  service_level: { label: 'Service level', text: 'Share of customer demand delivered in full, from the simulator. 100% means nothing goes unserved.' },
  revenue_at_risk: { label: 'Revenue at risk', text: 'Expected revenue lost to the problems found: each risk\'s simulated lost sales times its likelihood, added up.' },
  lead_time: { label: 'Avg delivery lead time', text: 'Average days from supplier to customer for the goods delivered today (flow-weighted).' },
  cover: { label: 'Days of stock cover', text: 'How many days customers\' and retailers\' stock lasts at normal demand if supply stops.' },
  resilience: { label: 'Resilience', text: 'How well the network survives its worst pairs of failures, 0 to 100 (Chaos Finder). Higher is safer.' },
  survival_clock: { label: 'Survival Clock', text: 'Days until stock runs out somewhere after a disruption starts.' },
  hhi: { label: 'HHI', text: 'Supplier concentration (Herfindahl index): 1.0 means one supplier provides everything; below 0.25 is diversified.' },
  spof: { label: 'Single point of failure', text: 'A site or lane whose loss alone cuts off customers or a large share of supply.' },
  unmet: { label: 'Unmet demand', text: 'Units customers wanted but did not receive.' },
  payback: { label: 'Payback', text: 'Years until the annual savings repay the build cost.' },
  simulated: { label: 'Simulated', text: 'Produced by the AEGIS digital twin on your network data, not observed in operations.' },
  severity: { label: 'Severity', text: 'Priority 0-100 from simulated impact, likelihood and customers affected. Critical ≥ 70, high ≥ 45, medium ≥ 25.' },
  shadow_price: { label: 'Shadow price', text: 'Extra demand served per extra unit of daily capacity at a site.' },
}
