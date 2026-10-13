/** Indian cities and logistics hubs for the builder's location picker (lat, lon to 3 decimals). */
export const INDIAN_CITIES = [
  ['Mumbai', 19.076, 72.878], ['Delhi', 28.614, 77.209], ['Bengaluru', 12.972, 77.595], ['Hyderabad', 17.385, 78.487],
  ['Ahmedabad', 23.023, 72.571], ['Chennai', 13.083, 80.271], ['Kolkata', 22.573, 88.364], ['Pune', 18.52, 73.857],
  ['Surat', 21.17, 72.831], ['Jaipur', 26.912, 75.787], ['Lucknow', 26.847, 80.947], ['Kanpur', 26.449, 80.331],
  ['Nagpur', 21.146, 79.088], ['Indore', 22.72, 75.858], ['Bhopal', 23.26, 77.413], ['Visakhapatnam', 17.686, 83.218],
  ['Patna', 25.594, 85.137], ['Vadodara', 22.307, 73.181], ['Ludhiana', 30.901, 75.857], ['Agra', 27.177, 78.008],
  ['Nashik', 19.998, 73.79], ['Coimbatore', 11.017, 76.956], ['Kochi', 9.931, 76.267], ['Madurai', 9.925, 78.12],
  ['Guwahati', 26.144, 91.736], ['Chandigarh', 30.733, 76.779], ['Bhubaneswar', 20.296, 85.825],
  ['Thiruvananthapuram', 8.524, 76.937], ['Raipur', 21.251, 81.63], ['Ranchi', 23.344, 85.31],
  ['Jamshedpur', 22.805, 86.203], ['Mysuru', 12.296, 76.639], ['Mangaluru', 12.914, 74.856],
  ['Vijayawada', 16.506, 80.648], ['Panaji (Goa)', 15.491, 73.828], ['Dehradun', 30.316, 78.032],
  ['Amritsar', 31.634, 74.872], ['Jodhpur', 26.238, 73.024], ['Rajkot', 22.304, 70.802], ['Gurugram', 28.459, 77.027],
  ['Noida', 28.535, 77.391], ['Sriperumbudur', 12.967, 79.942], ['Bhiwandi', 19.296, 73.063],
  ['Kandla Port', 23.033, 70.217], ['Thoothukudi Port', 8.764, 78.135],
].map(([name, lat, lon]) => ({ name, lat, lon }))

/** Case-insensitive prefix-then-substring search. */
export function searchCities(query, limit = 8) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return INDIAN_CITIES.slice(0, limit)
  const starts = INDIAN_CITIES.filter((c) => c.name.toLowerCase().startsWith(q))
  const contains = INDIAN_CITIES.filter((c) => !c.name.toLowerCase().startsWith(q) && c.name.toLowerCase().includes(q))
  return [...starts, ...contains].slice(0, limit)
}

/**
 * Rough outline of mainland India as [lon, lat] points: a faint backdrop for the offline builder map
 * (orientation only, not a political boundary).
 */
export const INDIA_OUTLINE = [
  [68.4, 23.6], [70.1, 24.3], [71.1, 24.6], [70.3, 25.8], [70.8, 27.8], [72.6, 29.0], [73.6, 30.0], [74.6, 31.0],
  [74.7, 32.5], [75.4, 32.9], [74.2, 34.0], [74.6, 35.1], [76.2, 35.8], [77.9, 35.4], [79.2, 33.9], [78.8, 32.5],
  [78.5, 31.2], [80.2, 30.3], [81.1, 30.0], [82.6, 28.9], [84.2, 27.4], [86.0, 26.6], [88.1, 26.4], [88.2, 27.9],
  [88.9, 27.3], [89.9, 26.8], [92.1, 26.9], [92.0, 27.8], [94.5, 29.2], [96.2, 29.4], [97.4, 28.2], [96.7, 27.3],
  [95.2, 26.6], [94.6, 25.2], [94.2, 23.8], [93.3, 22.9], [92.6, 21.9], [92.3, 23.6], [91.7, 22.9], [91.3, 24.0],
  [92.2, 24.9], [90.0, 25.3], [89.8, 25.9], [88.7, 26.2], [88.1, 24.6], [88.7, 23.2], [88.9, 22.0], [87.1, 21.5],
  [86.5, 20.0], [85.1, 19.3], [84.0, 18.2], [82.3, 16.6], [81.2, 15.9], [80.3, 15.0], [80.3, 13.4], [79.9, 11.2],
  [79.8, 10.3], [78.9, 9.2], [77.5, 8.1], [76.6, 8.9], [76.0, 10.4], [75.2, 12.0], [74.7, 13.3], [74.2, 14.8],
  [73.4, 16.5], [72.8, 19.0], [72.7, 21.0], [72.4, 22.2], [71.9, 21.4], [70.9, 20.7], [69.1, 22.3], [69.6, 22.8],
]
