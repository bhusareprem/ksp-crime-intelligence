# 06. A third-party provider changed its terms mid-project

**Outcome:** two wrong fixes before the right one, and a useful reminder that "it works"
and "it is right" are different claims.

---

## Symptom

The Intel Map rendered with **API KEY REQUIRED** stamped diagonally across every tile.

Nothing in the codebase had changed. CARTO began requiring an API key for the keyless
basemap endpoint that had worked for months. Any project using it saw the same thing.

## Fix 1: swap the provider

Replaced CARTO with Esri World Dark Gray Canvas, which is keyless and dark. Added a
fallback chain so a repeat of this failure degrades rather than breaks: after six tile
errors it falls through to OpenStreetMap, inverted by CSS so the fallback still matches
the dark interface.

Verified: 20 of 20 tiles from `services.arcgisonline.com`, zero CARTO requests.

## Then: "not a clean UI"

The watermarks were gone but the map still looked wrong. The assumption was that the
basemap was at fault, and the next question was whether to integrate Google Maps.

**Google Maps was the wrong answer, and worth recording why.** It has no keyless mode.
Without a billing-enabled key it stamps *"For development purposes only"* across every
tile, which is the same failure with a different logo, and with billing it charges per
map load. Swapping one watermark risk for another before a judged demo is not a fix.

Reading the actual rendering code showed the basemap was not the problem at all:

```python
r = 0.022 * Math.sqrt(idx)                      # ~2.4 km spiral
radius: Math.min(5 + n.score * 0.1, 13)         # up to 13px markers
```

At state zoom, **131 suspect markers scattered in 2.4 km spirals inside 31 large hotspot
circles**. They overlapped into blobs. Google Maps underneath would have looked identical.

## Fix 2: show less

The real fix was density, not tiles:

- Suspects appear only at zoom 8 and above, with a "Zoom in to plot individual suspects"
  hint at state level
- Hotspot circles toned down (fill 12% to 9%, thinner stroke)
- Spiral widened and markers shrunk so points separate instead of merging

State view went from 162 overlapping shapes to **31 clean district circles**, with 154
appearing on zoom-in.

## A bug found while verifying

Checking the result programmatically rather than by eye:

```
stateView: { zoom: 2, ... }        # expected 7
```

The map was resolving to whole-world zoom. Leaflet had measured the container before the
panel finished laying out, and `fitBounds` on a zero-size container produces a nonsense
zoom. It now re-measures across two frames and clamps:

```python
intelMapInstance.invalidateSize(false);
intelMapInstance.fitBounds(imAllBounds, { padding: [30, 30] });
if (intelMapInstance.getZoom() < 6) intelMapInstance.setView([14.7, 76.0], 7);
```

This had presumably been intermittent all along and would have been ugly on camera.

## Then: "it doesn't have names on the maps"

Also correct, and also my error. Esri splits its dark canvas into **two** layers:

- `World_Dark_Gray_Base`, landforms only
- `World_Dark_Gray_Reference`, every place name

Only the base had been added, producing an unlabelled silhouette. Both are now stacked,
with the labels brightened slightly so they stay readable over the hotspot circles.

Verified by reading pixels out of a label tile rather than trusting a 200 response:

```
tile: /tile/7/58/90
inkCoveragePct: 2.31
verdict: label tile contains drawn type/roads
```

A blank transparent overlay would also have returned HTTP 200 and 6 of 6 tiles loaded.

## Lessons

**A keyless third-party dependency can stop being keyless.** Both map providers now have
a fallback chain, since this will happen again.

**Diagnose before substituting.** Two of the three complaints here were about rendering
decisions in our own code, not the provider. Replacing the provider would have fixed
neither.

**"Loaded" is not "correct".** Tiles returned 200 while carrying a watermark; a label
layer would have returned 200 while being empty. The check has to assert the thing you
actually care about.
