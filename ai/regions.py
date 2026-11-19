"""Fixed region → state table for the one-sentence search (#38).  Owner: C.

The LLM may answer with a region name; the server, not the LLM, decides which
states that means. These are everyday U.S. regions, not the federal Scorecard
REGION codes (see docs/mgt656/technical.md).
"""

REGIONS = {
    "northeast": ("CT", "MA", "ME", "NH", "RI", "VT"),
    "mid_atlantic": ("DC", "DE", "MD", "NJ", "NY", "PA"),
    "south": ("AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN", "VA", "WV"),
    "midwest": ("IA", "IL", "IN", "KS", "MI", "MN", "MO", "ND", "NE", "OH", "SD", "WI"),
    "southwest": ("AZ", "NM", "OK", "TX"),
    "west": ("CO", "ID", "MT", "NV", "UT", "WY"),
    "pacific": ("AK", "CA", "HI", "OR", "WA"),
}

LABELS = {
    "northeast": "New England", "mid_atlantic": "Mid-Atlantic", "south": "the South", "midwest": "the Midwest",
    "southwest": "the Southwest", "west": "the Mountain West", "pacific": "the Pacific coast",
}
