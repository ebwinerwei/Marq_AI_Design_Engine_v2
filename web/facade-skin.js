import * as T from 'three';

// Use solved panel boundaries for both the WebGL facade texture and the
// triangle-clipped strokes in the Canvas fallback.
export function addFacadePanels(group, project, layout, colors, maxTextureSize, anisotropy, point, software = false) {
 const faces = new Map(project.faces.map(face => [face.id, face]));
 const byFace = new Map(layout.faces.map(face => [face.face, {face, pieces: [], seams: []}]));
 for (const piece of layout.pieces) {
  if (!piece.hidden) byFace.get(piece.face).pieces.push(piece);
 }
 for (const seam of layout.seams || []) byFace.get(seam.face).seams.push(seam);

 const areaBudget = 16 * 1024 * 1024 / Math.max(1, byFace.size);
 for (const {face, pieces, seams} of byFace.values()) {
  if (!pieces.length) continue;
  const {width, height} = face;
  const scale = Math.min(3072 / Math.max(width, height), maxTextureSize / Math.max(width, height),
                         Math.sqrt(areaBudget / (width * height)));
  const panelEdges = new Map();
  if (software) {
   for (const {panel, segments} of seams) {
    if (!panelEdges.has(panel)) panelEdges.set(panel, []);
    const dest = panelEdges.get(panel);
    for (const segment of segments) dest.push(segment.map(([u,v]) => point(faces.get(face.face),height,u,v)));
   }
  }
  const canvas = software ? null : document.createElement('canvas');
  const ctx = canvas?.getContext('2d');
  if (canvas) {
   canvas.width = Math.max(1, Math.round(width * scale));
   canvas.height = Math.max(1, Math.round(height * scale));
   ctx.scale(canvas.width / width, canvas.height / height);
   ctx.fillStyle = colors.Silver;
   ctx.fillRect(0, 0, width, height);
  }
  const batches = new Map();
  const source = faces.get(face.face);
  for (const {poly, finish, panel} of pieces) {
   if (ctx) {
    ctx.fillStyle = colors[finish];
    ctx.beginPath();
    ctx.moveTo(...poly[0]);
    for (let i = 1; i < poly.length; i++) ctx.lineTo(...poly[i]);
    ctx.closePath();
    ctx.fill();
   }
   if (!batches.has(finish)) batches.set(finish, {positions: [], uvs: [], edges: []});
   const batch = batches.get(finish);
   for (let i = 1; i + 1 < poly.length; i++) {
    if (software) batch.edges.push(panelEdges.get(panel) || []);
    for (const [u, v] of [poly[0], poly[i], poly[i+1]]) {
     batch.positions.push(...point(source, height, u, v).toArray());
     if (!software) batch.uvs.push(u / width, 1 - v / height);
    }
   }
  }
  let map = null;
  if (ctx) {
   ctx.beginPath();
   for (const seam of seams) {
    for (const [a, b] of seam.segments) {
     ctx.moveTo(...a);
     ctx.lineTo(...b);
    }
   }
   ctx.strokeStyle = '#68747c';
   // A drafting line in display space, independent of fabrication dimensions.
   ctx.lineWidth = Math.min(project.pitch * .10, Math.max(1.5 / scale, Math.max(width,height) / 850));
   ctx.stroke();
   map = new T.CanvasTexture(canvas);
   map.colorSpace = T.SRGBColorSpace;
   map.anisotropy = anisotropy;
  }
  for (const [finish, {positions, uvs, edges}] of batches) {
   const geometry = new T.BufferGeometry();
   geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
   if (software) geometry.userData.panelEdges = edges;
   else geometry.setAttribute('uv', new T.Float32BufferAttribute(uvs, 2));
   geometry.computeVertexNormals();
   const material = new T.MeshStandardMaterial({map, color:software ? colors[finish] : 0xffffff, side:T.DoubleSide, roughness:.8, metalness:.1,
    polygonOffset:true, polygonOffsetFactor:-2, polygonOffsetUnits:-2});
   material.userData.facadeFinish = finish;
   const mesh = new T.Mesh(geometry, material);
   mesh.castShadow = mesh.receiveShadow = true;
   group.add(mesh);
  }
 }
}
