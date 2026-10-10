# What the air is doing to sight: background haze, daylight, fog banks and
# gun smoke.
#
# All of it is expressed the same way, as an *extinction coefficient*
# (sigma, per metre): light travelling d metres through air of extinction
# sigma keeps a fraction exp(-sigma * d) of its contrast (Beer-Lambert).
# The vision code integrates sigma along each line of sight, so haze, a fog
# bank and a drifting cloud of powder smoke all obscure things by the same
# mechanism, just with different densities, shapes and heights.
#
# Meteorological visibility V (the distance at which a dark object is just
# discernible against the horizon) relates to sigma via Koschmieder's law,
# V = 3.912 / sigma - which lets scenarios be written in the natural unit
# ("visibility 400 m in the fog") while the maths stays uniform.
#
# Volumes have a *top* height: fog lies low, powder smoke hangs at deck
# height. A line of sight passing above a volume isn't affected by it,
# which is what lets a lookout at the masthead - or the topsails of an
# enemy - show above the smoke of a broadside.

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from broadside.sim.units import value_noise

KOSCHMIEDER = 3.912


def sigma_for_visibility(visibility_m: float) -> float:
    return KOSCHMIEDER / max(visibility_m, 1.0)


@dataclass
class FogBank:
    """An elliptical bank of fog with ragged edges, drifting with the wind.

    `visibility_m` is the visibility deep inside the bank; density falls
    off smoothly over the outer `edge_fraction` of its radius, and a noise
    field makes the edge wispy rather than a hard ellipse."""

    x: float
    y: float
    radius_x: float
    radius_y: float
    visibility_m: float = 120.0
    top_m: float = 35.0
    angle_degrees: float = 0.0
    edge_fraction: float = 0.35
    drift_factor: float = 0.6  # fraction of wind speed the bank moves at
    seed: int = 0

    @property
    def sigma(self) -> float:
        return sigma_for_visibility(self.visibility_m)

    def bbox(self) -> tuple[float, float, float, float]:
        r = max(self.radius_x, self.radius_y) * 1.3
        return self.x - r, self.y - r, self.x + r, self.y + r

    def density(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        a = math.radians(self.angle_degrees)
        dx = xs - self.x
        dy = ys - self.y
        u = dx * math.cos(a) - dy * math.sin(a)
        v = dx * math.sin(a) + dy * math.cos(a)
        q = np.sqrt((u / self.radius_x) ** 2 + (v / self.radius_y) ** 2)
        # Wisps: perturb the normalised radius with noise that moves with
        # the bank (sampled in bank-relative coordinates).
        q = q * (0.8 + 0.4 * value_noise(u, v, max(self.radius_x, self.radius_y) * 0.25, self.seed))
        core = 1.0 - self.edge_fraction
        t = np.clip((1.0 - q) / max(self.edge_fraction, 1e-6), 0.0, 1.0)
        t = np.where(q < core, 1.0, t * t * (3 - 2 * t))
        return self.sigma * t


@dataclass
class SmokePuff:
    """One gun's discharge of powder smoke: a gaussian blob that drifts
    downwind, spreads, and thins out. `sigma_peak` is the extinction at the
    centre; it falls as the puff expands (the smoke spreads over a larger
    area) and as it slowly disperses."""

    x: float
    y: float
    vx: float  # m/s, own momentum from the muzzle blast, decays quickly
    vy: float
    radius: float = 4.0
    sigma_peak: float = 0.6
    top_m: float = 9.0
    age: float = 0.0
    # "smoke" (powder smoke: lingers, rises) | "dust" (stone and sand from
    # shot and falling masonry: heavy, settles fast, hugs the ground) |
    # "spray" (a shot's splash: gone in seconds).
    kind: str = "smoke"

    def bbox(self) -> tuple[float, float, float, float]:
        r = self.radius * 2.6
        return self.x - r, self.y - r, self.x + r, self.y + r


# How often a squall comes up, per hour of sea time. Rare enough to be
# weather and not a nuisance; often enough that a long passage meets one.
SQUALL_CHANCE_PER_HOUR = 0.12


@dataclass
class Atmosphere:
    """Scene-wide weather state affecting sight: haze visibility, light
    level, fog banks and smoke."""

    haze_visibility_m: float = 12000.0
    light: float = 1.0  # 1 = full daylight, ~0.3 dusk, ~0.1 moonlit night
    fog_banks: list[FogBank] = field(default_factory=list)
    smoke: list[SmokePuff] = field(default_factory=list)
    # Weather on your back. `rain` is 0..1: drizzle at 0.3, a downpour at
    # 0.8. A squall is a short, violent affair - wind up, rain on, sight
    # down - and the thing that catches a ship with too much canvas set.
    rain: float = 0.0
    squall_until_s: float = -1.0
    squall_gust_knots: float = 0.0
    clear_visibility_m: float = 12000.0
    # The weather over the whole sea, as a field in place and time
    # (sim/world/weather.py). The atmosphere reads it where the ship is;
    # the view reads it per cell, for cloud shadows.
    weather: object = None
    cloud: float = 0.0
    fog_level: float = 0.0

    # Smoke behaviour, tuned so a broadside's smoke hangs for a minute or
    # two in a moderate breeze, as period accounts describe.
    smoke_growth_mps: float = 0.35
    smoke_half_life_s: float = 55.0
    smoke_min_sigma: float = 0.004  # below this a puff no longer marks the sky it's in
    smoke_min_column: float = 0.01  # sigma * radius: below this the puff is dropped
    smoke_rise_mps: float = 0.05
    smoke_max_top_m: float = 16.0

    @property
    def haze_sigma(self) -> float:
        """Background extinction everywhere. Darkness is modelled as a loss
        of effective visibility: at night the same air lets you see far
        less far, which is the mechanically relevant part."""
        light = max(self.light, 0.02)
        return sigma_for_visibility(self.haze_visibility_m * light)

    def effective_visibility_m(self) -> float:
        return KOSCHMIEDER / self.haze_sigma

    # --- Evolution ------------------------------------------------------

    # --- Weather --------------------------------------------------------

    def weather_tick(self, dt: float, now_s: float, rng, x: float = 0.0, y: float = 0.0, wind_knots: float = 10.0, wind_vx: float = 0.0, wind_vy: float = 0.0) -> dict:
        """What the weather is doing where the ship is. The pattern itself
        lives in the field and drifts downwind; this reads it, eases the
        local values toward it, and reports anything worth saying.

        Returns a dict of news for the log.
        """
        news: dict = {}
        if self.clear_visibility_m <= 0.0:
            self.clear_visibility_m = self.haze_visibility_m
        field = self.weather
        if field is not None:
            field.tick(dt, wind_vx, wind_vy)
            want_cloud = field.rain(x, y)
            cover = float(field.cloud(np.array([x]), np.array([y]))[0])
            fogginess = field.fogginess(x, y, wind_knots)
            was_rain = self.rain > 0.15
            was_fog = self.fog_level > 0.2
            # Ease toward the field's values: weather arrives, it does not
            # switch on.
            k = min(1.0, dt / 90.0)
            self.rain += (want_cloud - self.rain) * k
            self.cloud += (cover - self.cloud) * min(1.0, dt / 120.0)
            self.fog_level += (fogginess - self.fog_level) * min(1.0, dt / 240.0)
            self.squall_gust_knots = max(0.0, 14.0 * self.rain * (0.6 + 0.4 * field.gust(x, y)))
            if self.rain > 0.15 and not was_rain:
                news["rain"] = self.rain
            elif was_rain and self.rain <= 0.15:
                news["clearing"] = True
            if self.fog_level > 0.2 and not was_fog:
                news["fog"] = self.fog_level
            elif was_fog and self.fog_level <= 0.2:
                news["fog_clearing"] = True
        else:
            squalling = now_s < self.squall_until_s
            if squalling:
                self.rain = min(1.0, self.rain + dt / 120.0)
            else:
                if self.squall_until_s > 0.0 and self.rain > 0.0 and self.rain - dt / 300.0 <= 0.0:
                    news["clearing"] = True
                self.rain = max(0.0, self.rain - dt / 300.0)
                self.squall_gust_knots = 0.0
        if now_s < self.squall_until_s:
            # A squall put on deliberately (a scenario, or the field's own
            # instability peaking) overrides the gentler background.
            self.rain = min(1.0, self.rain + dt / 90.0)
            if self.squall_gust_knots <= 0.0:
                self.squall_gust_knots = 14.0
        # Rain and mist thicken the air: a downpour cuts sight to a mile or
        # less, and a thick fog to a few hundred yards.
        self.haze_visibility_m = self.clear_visibility_m * (1.0 - 0.75 * self.rain) * (1.0 - 0.85 * self.fog_level)
        return news

    def light_at(self, xs, ys):
        """The light falling on these points: the day's light, less the
        shadow of whatever cloud is over them."""
        if self.weather is None:
            return np.full(np.shape(xs), self.light)
        return self.light * self.weather.shade(xs, ys)

    def words(self) -> str:
        from broadside.sim.world.weather import weather_words

        return weather_words(self.cloud, self.rain, self.fog_level)

    def tick(self, dt: float, wind_vx: float, wind_vy: float) -> None:
        for bank in self.fog_banks:
            bank.x += wind_vx * bank.drift_factor * dt
            bank.y += wind_vy * bank.drift_factor * dt

        decay = 0.5 ** (dt / self.smoke_half_life_s)
        decay_by_kind = {"smoke": decay, "dust": 0.5 ** (dt / 14.0), "spray": 0.5 ** (dt / 1.5)}
        keep: list[SmokePuff] = []
        for p in self.smoke:
            p.age += dt
            p.x += (wind_vx * 0.85 + p.vx) * dt
            p.y += (wind_vy * 0.85 + p.vy) * dt
            p.vx *= 0.9 ** (dt * 10)
            p.vy *= 0.9 ** (dt * 10)
            old_r = p.radius
            # Fast initial billow, slowing as it grows.
            p.radius += self.smoke_growth_mps * dt * (1.0 + 4.0 / (1.0 + p.age))
            p.sigma_peak *= (old_r / p.radius) ** 2 * decay_by_kind.get(p.kind, decay)
            if p.kind == "smoke":
                p.top_m = min(self.smoke_max_top_m, p.top_m + self.smoke_rise_mps * dt)
            else:
                p.top_m = max(1.5, p.top_m - 0.15 * dt)  # dust and spray settle
            # Drop a puff once the whole column through it is negligible -
            # judged on sigma * radius, not peak sigma, because a big thin
            # cloud can still obscure plenty along a long line of sight.
            if p.sigma_peak * p.radius > self.smoke_min_column:
                keep.append(p)
        self.smoke = keep

    def emit_smoke(self, x: float, y: float, vx: float = 0.0, vy: float = 0.0, *, radius: float = 4.0, sigma_peak: float = 0.6, kind: str = "smoke", top_m: float | None = None) -> None:
        top = top_m if top_m is not None else {"smoke": 9.0, "dust": 7.0, "spray": 4.0}.get(kind, 9.0)
        self.smoke.append(SmokePuff(x=x, y=y, vx=vx, vy=vy, radius=radius, sigma_peak=sigma_peak, top_m=top, kind=kind))

    # --- Sampling -------------------------------------------------------

    def fog_at(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(sigma, top_m) of fog at each point."""
        sigma = np.zeros(xs.shape)
        top = np.zeros(xs.shape)
        for bank in self.fog_banks:
            x0, y0, x1, y1 = bank.bbox()
            sel = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
            if not sel.any():
                continue
            d = bank.density(xs[sel], ys[sel])
            sigma[sel] += d
            top[sel] = np.where(d > 0, np.maximum(top[sel], bank.top_m), top[sel])
        return sigma, top

    def smoke_at(self, xs: np.ndarray, ys: np.ndarray, kind: str | None = None) -> tuple[np.ndarray, np.ndarray]:
        """(sigma, top_m) of smoke, dust and spray at each point (or of one
        kind only)."""
        sigma = np.zeros(xs.shape)
        top = np.zeros(xs.shape)
        if xs.size == 1:
            # One point: plain arithmetic. A battle asks this question
            # hundreds of times a second and numpy's per-call overhead
            # dwarfs the work.
            x = float(xs.reshape(-1)[0])
            y = float(ys.reshape(-1)[0])
            s = 0.0
            t = 0.0
            for p in self.smoke:
                if kind is not None and p.kind != kind:
                    continue
                dx = x - p.x
                dy = y - p.y
                r = p.radius
                if abs(dx) > 2.5 * r or abs(dy) > 2.5 * r:
                    continue
                d = p.sigma_peak * math.exp(-(dx * dx + dy * dy) / (2.0 * r * r))
                s += d
                if d > 1e-5 and p.top_m > t:
                    t = p.top_m
            sigma.reshape(-1)[0] = s
            top.reshape(-1)[0] = t
            return sigma, top
        for p in self.smoke:
            if kind is not None and p.kind != kind:
                continue
            x0, y0, x1, y1 = p.bbox()
            sel = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
            if not sel.any():
                continue
            d2 = (xs[sel] - p.x) ** 2 + (ys[sel] - p.y) ** 2
            d = p.sigma_peak * np.exp(-d2 / (2.0 * p.radius * p.radius))
            sigma[sel] += d
            top[sel] = np.where(d > 1e-5, np.maximum(top[sel], p.top_m), top[sel])
        return sigma, top
