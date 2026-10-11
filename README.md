# Bhachakra — backend

The calculation server behind **Bhachakra** (भचक्र, "the wheel of stars"), a Vedic
astrology (Jyotish) app.

A FastAPI service that computes:

- planetary positions (sidereal, with a choice of ayanamsha), retrograde and speed
- houses and the ascendant
- divisional charts (vargas)
- Vimshottari dasha
- aspects
- planetary strength
- panchanga — tithi, nakshatra, yoga, karana and a sunrise-based vara, with sunrise/sunset
- place lookup (geocoding)

## Run it

Requires Python 3.12.

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # then fill in your own values
uvicorn main:app --reload
```

The interactive API docs are then at http://127.0.0.1:8000/docs

## Credits

Astronomical calculations use the **Swiss Ephemeris** by Astrodienst AG
(https://www.astro.com/swisseph/), through the `pyswisseph` Python binding.
The Swiss Ephemeris is licensed under the GNU AGPL (or a commercial licence from
Astrodienst), which is why this backend is published under the AGPL.

## Licence

Copyright © 2026 Bhachakra

This program is free software: you can redistribute it and/or modify it under the
terms of the GNU Affero General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.
See [LICENSE](LICENSE) for the full text.

Only this backend is open source. The Bhachakra app (frontend) is a separate
program that talks to this server over HTTP and is not part of this repository.
