This directory supplies a read-only lighting check for the private ParallaxGen
outputs. It imports the pure Python `nifgen` bundled in the official NifTools
addon v0.1.1 release. It never imports Blender, runs the blocked native helper,
starts a GUI/game, or saves a NIF.

`lighting_schema.py` exposes these functions:

- `snapshot(path)` reads all supported shapes in header block order without
  deduplicating names. Each row includes the actual block ID, shader block ID,
  real child-ordinal paths, effective vertex data count/storage, attribute flags,
  normal/tangent/bitangent payloads and color payloads. SSE normalized bytes are
  recovered with the author's inverse codec; LE attributes retain float32 bits.
- `rgb8_hsl_operation(rgb, lum_mult=None, sat_mult=None)` reproduces the pinned
  Boost.GIL 1.86/PG RGB8 → HSL32 → multiplier/clamp → RGB8 arithmetic, rounding
  every elementary operation to float32. Alpha is unchanged.
- `apply_color_recipes(shape, ordered_recipes)` replays one *selected* ordered
  rule group. Within each rule, a color-presence toggle happens first, followed
  by the combined luminance/saturation operation. Enabling colors initializes
  white only on the false → true transition. Disabling then enabling resets
  white. LE NiTriShape colors do not receive the PG HSL multiplier because the
  pinned native code applies it only to BSTriShape/BSMeshLODTriShape.
- `compare_shape(before, after, ordered_recipes, stream,
  allow_serializer_rebuild=False)` checks lighting and descriptor fields.
  Without `smooth_angle`, normal/tangent/bitangent encodings remain exact.
  With a proven explicit recipe, the arrays require complete finite values,
  vertex counts and unit vectors. Color output must match the replay exactly;
  a one-byte RGB difference fails.
- `compare_descriptor(...)` preserves all non-lighting flags and reserved bits.
  Only explicitly authorized normal/tangent/color flags can change. It rebuilds
  every stride and offset using the exact pinned Nifly `CalcDataSizes` algorithm,
  and verifies shape/skin-partition/per-partition descriptors and byte counts.
  Extra-float vertex layouts unsupported by the bundled schema stop. Unknown
  layout changes are never accepted by masking the whole descriptor.
- `normalization_allowance(...)` first runs the full lighting and descriptor
  comparison. Only after PASS does it return exact permitted CAPI property
  changes for `hasNormals`, `hasVertexColors`, and `vertexDesc`. The parent must
  apply this allowance only to the paired shape node; all other properties and
  non-shape nodes remain exact.

Pair shapes by the preserved scene-child paths/block mapping. Names are labels,
not unique IDs. `source_shader_block_id` is a real reference to `n.blocks`, for
both SSE and LE. BSDynamicTriShape bitangent X comes from its dynamic Vector4.w
stream, matching the pinned native Nifly preparation path. Skin-partition vertex
data comes from the author's `get_vertex_data()` helper.

The unit-vector bound for packed SSE normal/tangent channels is
`sqrt(3)/255 + 4*2^-23`: nearest normalized-byte quantization has step `2/255`
and maximum error `1/255` per component. Float32 LE vectors use `1e-5`. Zero or
nonunit vectors produced by a declared recipe stop for a separate geometric
explanation; there is no blanket exception. This does not establish native
rendering or visual quality.

The parent owns rule selection and provenance. `ordered_recipes` must represent
one actual winning JSON group with its exact source file hash and entry order,
including any old alternate-TXST texture context. This module does not infer a
winning mod/rule from its filename. A valid unit vector alone is insufficient
authorization to change it. All positions, triangles, UVs, node transforms,
bones, weights, skin transforms and partitions still require the independent
parent geometry validator.

`allow_serializer_rebuild` is false by default. A caller may enable it only with
separate proof of the pinned unconditional `FinalizeData` canonical layout
rebuild and complete geometry equality. Even then, flags/reserved bits remain
protected and the new descriptor must equal the exact derived value. This is
not a field-wide relaxation.

The 16 checks in `fixture_report.json` passed. The three real fixtures cover
14 ordinary SSE shapes, six SSE skin-partition shapes, and seven LE shapes;
their counts match the parent's existing author-API geometry snapshots.
Color fixtures include a 4,096-color RGB identity grid, every gray value, clamp
and rounding examples, an actual SSE palette replay and unchanged alpha.
Mutation checks reject unexpected normal/tangent/bitangent changes, bad RGB
bytes, UV/full-precision/reserved descriptor flags and incorrect offsets.
The fixtures are static checks, not an actual PG run or a native render test.

Native PG `GetTree` 3D indices are deliberately not guessed from header order.
The parent should use the actual native trace/witness and verify its final
alternate-texture mapping. Source trailers and nonfinite source geometry are
not repaired or accepted merely because this lighting module can inspect data.

Provenance is pinned in `fixture_report.json`: the official NifTools release,
Boost.GIL 1.86, PG0.9.9.5 `PatcherMeshShaderTruePBR.cpp`, and PG's exact Nifly
submodule `c3cbdd64f18eb45f0b54975591f75db1ec5e6df0`. The HSL algorithm follows
Christian Henning's 2012 Boost.GIL implementation under the Boost Software
License1.0. Descriptor logic follows the separately preserved Nifly GPLv3
sources. Original license/source files remain in the pinned primary-source
directories.
