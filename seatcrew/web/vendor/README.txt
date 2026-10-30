model-viewer.min.js - @google/model-viewer 4.4.0 (Apache-2.0, see model-viewer.LICENSE.txt), bundles three.js (MIT) and lit (BSD-3-Clause).
Vendored so the 3D viewer works offline with no CDN. Only Draco/KTX2-compressed GLBs (some cloud 3D outputs) make model-viewer fetch a decoder from gstatic.com; plain GLBs (incl. the offline standee) need no network.
