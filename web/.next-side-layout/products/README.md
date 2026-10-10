# Product illustrations

70 individual transparent WebP illustrations extracted from two sheets generated with
the built-in image generation tool. Each subject has its own measured bounding box;
the UI does not crop a uniform grid at runtime.
These are decorative produce illustrations, not photographs of the shelf or exact packaging.
The source PNGs are preserved in the Codex generated-images directory.

Prompt specification: photorealistic studio produce cutouts, transparent alpha, no text,
no packaging branding, consistent lighting, one centered product type per uniform cell.
`p0-*.webp`: vegetables, citrus, apples, pears and melons.
`p1-*.webp`: tomatoes, berries, tropical fruit and stone fruit.
The exact cell order and product-name mapping are in `app/product-image.tsx`.

Export: 128 × 128 pixels, eight-pixel transparent padding, WebP quality 85, preserved
alpha. Once store data arrives, thumbnails preload and decode in a six-request queue,
prioritizing products with tasks. They are served locally without third-party requests.
