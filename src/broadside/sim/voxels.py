# Voxel structures: walls, forts and buildings made of blocks that crack,
# break, fall and pile up as rubble.
#
# A ship's hull is modelled per 1 m deck tile (sim/structure.py) because a
# ship is essentially one deck seen from above. A fortification wall needs
# its third dimension: shot knocks out blocks *partway up*, and what's
# above a hole either arches over it or comes down. So walls are voxel
# grids - 0.5 m blocks of masonry by default - each with a material and an
# integrity:
#
#   impact    a ball entering a block spends kinetic energy to break it
#             (break energy = material toughness x ENERGY_PER_TOUGHNESS);
#             if it has energy left it carries on into the next block, if
#             not it lodges. Neighbouring blocks are cracked by spalling,
#             worst on the far face as the ball punches through.
#   support   a block stands if the block under it stands; masonry can
#             also arch over a short gap (up to ARCH_SPAN blocks sideways
#             from a supported block). Anything else is unsupported.
#   crushing  badly cracked blocks carrying a tall column above them fail.
#   falling   unsupported blocks drop a block per tick (loose now - rubble),
#             landing on whatever is below; loose rubble slides off steep
#             piles to its angle of repose. Every landing throws up dust.
#
# See docs/design/15_physics_sandbox.md.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from broadside.sim import components as c
from broadside.sim.structure import MAT_BY_CODE, MAT_CODES

ENERGY_PER_TOUGHNESS_J = 120_000.0  # a 0.5 m block of masonry (toughness 4) takes ~480 kJ
ARCH_SPAN = 1  # masonry bridges a half-metre gap, not much more
CRUSH_INTEGRITY = 0.35
CRUSH_LOAD = 5  # blocks above


@dataclass
class VoxelStructure:
    name: str
    voxel_m: float
    material: np.ndarray  # [z, y, x] int16 material code, -1 = empty
    integrity: np.ndarray  # [z, y, x] 0..1
    loose: np.ndarray  # [z, y, x] bool: rubble, not bonded masonry
    base_z_m: float  # height of the grid's floor above the waterline
    destroyed: int = 0
    fallen: int = 0
    impacts: list = field(default_factory=list)  # [(time_s, x, y, z)] recent hits (local voxel coords)
    dirty: bool = True

    @property
    def shape(self):
        return self.material.shape  # (nz, ny, nx)

    @property
    def solid(self) -> np.ndarray:
        return self.material >= 0

    def local_to_voxel(self, u, v, z_m):
        nz, ny, nx = self.shape
        vm = self.voxel_m
        ix = np.floor(u / vm + nx / 2.0).astype(np.int64)
        iy = np.floor(v / vm + ny / 2.0).astype(np.int64)
        iz = np.floor((z_m - self.base_z_m) / vm).astype(np.int64)
        return ix, iy, iz

    def voxel_centre_local(self, ix, iy, iz):
        nz, ny, nx = self.shape
        vm = self.voxel_m
        return (ix + 0.5 - nx / 2.0) * vm, (iy + 0.5 - ny / 2.0) * vm, self.base_z_m + (iz + 0.5) * vm

    def column_top_m(self) -> np.ndarray:
        """[y, x] height (above the waterline) of the highest block, or 0."""
        nz = self.shape[0]
        solid = self.solid
        any_ = solid.any(axis=0)
        top = nz - 1 - np.argmax(solid[::-1], axis=0)
        return np.where(any_, self.base_z_m + (top + 1) * self.voxel_m, 0.0)


def build_wall(length_m: float, thickness_m: float, height_m: float, *, base_z_m: float, material: str = "masonry", voxel_m: float = 0.5, margin_m: float = 3.0, name: str = "curtain wall") -> VoxelStructure:
    """A straight wall along the local u axis (length), v = thickness, with a
    margin of empty ground around it for rubble to spill into."""
    nx = int(round((length_m + 2 * margin_m) / voxel_m))
    ny = int(round((thickness_m + 2 * margin_m) / voxel_m))
    nz = int(round(height_m / voxel_m)) + 2
    mat = np.full((nz, ny, nx), -1, dtype=np.int16)
    m = int(round(margin_m / voxel_m))
    wx = int(round(length_m / voxel_m))
    wy = int(round(thickness_m / voxel_m))
    wz = int(round(height_m / voxel_m))
    mat[:wz, m : m + wy, m : m + wx] = MAT_CODES[material]
    integ = np.where(mat >= 0, 1.0, 0.0)
    # Crenellations: every other block on the top course removed.
    mat[wz - 1, m : m + wy, m : m + wx : 2] = -1
    integ[wz - 1, m : m + wy, m : m + wx : 2] = 0.0
    return VoxelStructure(name, voxel_m, mat, integ, np.zeros(mat.shape, dtype=bool), base_z_m)


def break_energy(vs: VoxelStructure, ix: int, iy: int, iz: int) -> float:
    mat = MAT_BY_CODE[int(vs.material[iz, iy, ix])]
    e = mat.toughness * ENERGY_PER_TOUGHNESS_J * (vs.voxel_m / 0.5) ** 3
    return e * (0.35 if vs.loose[iz, iy, ix] else 1.0)


def _crack(vs: VoxelStructure, ix: int, iy: int, iz: int, energy: float) -> None:
    nz, ny, nx = vs.shape
    if 0 <= ix < nx and 0 <= iy < ny and 0 <= iz < nz and vs.material[iz, iy, ix] >= 0:
        vs.integrity[iz, iy, ix] = max(0.0, vs.integrity[iz, iy, ix] - energy / break_energy(vs, ix, iy, iz))
        if vs.integrity[iz, iy, ix] <= 0.0:
            _remove(vs, ix, iy, iz)


def _remove(vs: VoxelStructure, ix: int, iy: int, iz: int) -> None:
    vs.material[iz, iy, ix] = -1
    vs.integrity[iz, iy, ix] = 0.0
    vs.loose[iz, iy, ix] = False
    vs.destroyed += 1
    vs.dirty = True


def impact(state, ent: int, vs: VoxelStructure, ix: int, iy: int, iz: int, energy_j: float, dir_local: tuple) -> tuple[float, int]:
    """A ball with `energy_j` enters block (ix, iy, iz) travelling along
    `dir_local` (unit vector in grid axes x, y, z). Returns (energy left,
    blocks broken). The caller keeps flying the ball if energy is left."""
    cost = break_energy(vs, ix, iy, iz) * max(0.05, float(vs.integrity[iz, iy, ix]))
    vs.impacts.append((state.now_s, ix, iy, iz))
    vs.impacts = [i for i in vs.impacts if state.now_s - i[0] < 5.0]
    vs.dirty = True
    dx, dy, dz = dir_local
    if energy_j >= cost:
        _remove(vs, ix, iy, iz)
        left = energy_j - cost
        # Spalling: neighbours cracked, the far side worst (the ball punches
        # a cone of debris out of the back face).
        for ox, oy, oz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            behind = ox * dx + oy * dy + oz * dz > 0.5
            _crack(vs, ix + ox, iy + oy, iz + oz, cost * (0.35 if behind else 0.15))
        return left, 1
    vs.integrity[iz, iy, ix] -= energy_j / break_energy(vs, ix, iy, iz)
    for ox, oy, oz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)):
        _crack(vs, ix + ox, iy + oy, iz + oz, energy_j * 0.12)
    return 0.0, 0


def supported(vs: VoxelStructure) -> np.ndarray:
    """[z, y, x] bool: blocks that stand. Loose rubble only stands on what's
    directly below it; bonded masonry can arch ARCH_SPAN blocks sideways."""
    solid = vs.solid
    nz = solid.shape[0]
    sup = np.zeros_like(solid)
    sup[0] = solid[0]
    for z in range(1, nz):
        layer = solid[z] & sup[z - 1]
        bonded = solid[z] & ~vs.loose[z]
        grow = layer.copy()
        for _ in range(ARCH_SPAN):
            g = grow.copy()
            g[1:, :] |= grow[:-1, :]
            g[:-1, :] |= grow[1:, :]
            g[:, 1:] |= grow[:, :-1]
            g[:, :-1] |= grow[:, 1:]
            grow = g & bonded | layer
        sup[z] = grow
    return sup


def collapse_step(state, ent: int, vs: VoxelStructure, pose, rng) -> int:
    """One tick of crushing, falling and sliding. Returns blocks that moved."""
    if not vs.dirty:
        return 0
    nz, ny, nx = vs.shape
    solid = vs.solid
    moved = 0
    landed = []
    # Crushing: cracked blocks under a tall load give way.
    load = np.cumsum(solid[::-1], axis=0)[::-1] - solid
    crush = solid & ~vs.loose & (vs.integrity < CRUSH_INTEGRITY) & (load >= CRUSH_LOAD)
    for iz, iy, ix in zip(*np.nonzero(crush)):
        if rng.random() < 0.3:
            vs.loose[iz, iy, ix] = True
            vs.integrity[iz, iy, ix] *= 0.5
            moved += 1
    sup = supported(vs)
    falling = vs.solid & ~sup
    # Drop unsupported blocks one level (bottom-up so columns fall together).
    for iz in range(1, nz):
        ys, xs = np.nonzero(falling[iz])
        for iy, ix in zip(ys, xs):
            if vs.material[iz - 1, iy, ix] < 0:
                vs.material[iz - 1, iy, ix] = vs.material[iz, iy, ix]
                vs.integrity[iz - 1, iy, ix] = vs.integrity[iz, iy, ix] * 0.7
                vs.loose[iz - 1, iy, ix] = True
                vs.material[iz, iy, ix] = -1
                vs.integrity[iz, iy, ix] = 0.0
                vs.loose[iz, iy, ix] = False
                vs.fallen += 1
                moved += 1
                if iz - 1 == 0 or vs.material[iz - 2, iy, ix] >= 0:
                    landed.append((ix, iy, iz - 1))
            else:
                vs.loose[iz, iy, ix] = True  # resting on something: now rubble
    # Rubble slides off steep piles (angle of repose ~ one block per block).
    for iz in range(1, nz):
        ys, xs = np.nonzero(vs.loose[iz] & (vs.material[iz] >= 0))
        for iy, ix in zip(ys, xs):
            if rng.random() > 0.35:
                continue
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                tx, ty = ix + ox, iy + oy
                if 0 <= tx < nx and 0 <= ty < ny and vs.material[iz, ty, tx] < 0 and vs.material[iz - 1, ty, tx] < 0:
                    vs.material[iz - 1, ty, tx] = vs.material[iz, iy, ix]
                    vs.integrity[iz - 1, ty, tx] = vs.integrity[iz, iy, ix]
                    vs.loose[iz - 1, ty, tx] = True
                    vs.material[iz, iy, ix] = -1
                    vs.integrity[iz, iy, ix] = 0.0
                    vs.loose[iz, iy, ix] = False
                    moved += 1
                    landed.append((tx, ty, iz - 1))
                    break
    if landed:
        _dust(state, vs, pose, landed)
    if moved == 0 and not crush.any():
        vs.dirty = False
    return moved


def _dust(state, vs: VoxelStructure, pose, voxels: list) -> None:
    x, y, head = pose
    fx, fy = math.sin(math.radians(head)), math.cos(math.radians(head))
    sx, sy = fy, -fx
    # One puff per cluster of landings (cheap), sized by how much came down.
    k = len(voxels)
    mx = sum(v[0] for v in voxels) / k
    my = sum(v[1] for v in voxels) / k
    u, v, _z = vs.voxel_centre_local(mx, my, 0)
    wx, wy = x + u * fx + v * sx, y + u * fy + v * sy
    state.atmosphere.emit_smoke(wx, wy, radius=1.5 + 0.3 * math.sqrt(k), sigma_peak=min(0.6, 0.12 + 0.04 * k), kind="dust")


def structure_system(state, dt: float) -> None:
    world = state.world
    rng = state.rng.stream("structures")
    for ent, (vs, pos, head) in world.get_components(VoxelStructure, c.WorldPosition, c.Heading):
        collapse_step(state, ent, vs, (pos.x_m, pos.y_m, head.degrees), rng)
