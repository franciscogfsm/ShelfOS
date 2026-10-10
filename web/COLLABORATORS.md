# Demo dos colaboradores

Run `npm run dev` at the repository root and open `/colaboradores` on the frontend URL printed in the terminal. The phone icon in the dashboard also opens it.

The page uses the same latest shelf predictions as the dashboard (or the bundled snapshot when the backend cannot be reached). It shows tasks only, with catalogue illustrations and a schematic of the exact area polygon; no camera images are loaded.

Camera IDs and area polygons are real. Physical locations are **simulated**, defined in `app/colaboradores/locations.ts`: two zones, seven bays each. Replace this mapping with surveyed store locations before using physical directions. There is no GPS or indoor tracking: “Já estou aqui” updates the simulated position.

Empty shelves take priority, then wrong products, then low stock. Within each priority, the next nearest mapped bay is selected using the demo floor plan. This is a walking-order heuristic, not a measured shortest route.

Tap “Já estou aqui” and check the highlighted shelf position. The page polls the existing store API every eight seconds while visible. A newer image confirms a task when the area is full, compliant, unobstructed (at most 25%) and confident (stock and product at least 65%). Memory answers and unchanged captures cannot confirm completion. This observes new backend predictions; it does not capture images from a physical camera itself.

“Simular reposição · DEMO” demonstrates the analysis animation and next task after 2.6 seconds. It is clearly labelled as simulated and never modifies predictions. Simulated completion is saved in this browser, keyed to the prediction frame. Real confirmations are retained for the current page session. “Reiniciar demo” clears demo progress; it does not undo actual shelf state or synchronize devices.

The map uses lightweight isometric SVG geometry with supermarket fixtures, checkout counters and the route to a shelf. No WebGL engine or image textures are loaded. The department context and physical plan remain simulated.

Verification tests: `cd web` then `node --test scripts/staff.test.mjs`.

`npm run build` exports the route; the Python server serves both `/colaboradores` and `/colaboradores/` after restart.
