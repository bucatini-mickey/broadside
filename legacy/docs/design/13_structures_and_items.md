# Structures, Items, Collision and Boarding

The "everything is a point of data" layer. Every ship is simulated at the same granularity as yours: every square metre of her is a piece of something with a condition, every cask has its contents recorded, and every one of her people is a full person (`11_people.md`). Ships can collide, foul each other, and be boarded man by man. Code: `sim/structure.py`, `sim/items.py`, `sim/systems/boarding.py`.

**Status: groundwork, proven end to end** by the `boarding_action` scenario. A sloop runs aboard a French brig; the hulls foul where their tiles overlap, damaging those planks; boarders cross over the rails; and individual fights wound specific body parts until men bleed out.

## Structure: materials and condition per tile

- A ship class's **deck plan** (`sim/shiplayout.py`) is shared, read-only data. Each **individual ship** carries a `StructureState`: arrays over the same 1 m grid giving, per tile, its **material**, its **integrity** (1 = sound, 0 = gone) and **fire**.
- Materials (`MATERIALS`) have toughness, flammability, splinter tendency and density: **oak** hull and bulwarks (throws killing splinters when struck), **pine** deck planking, **fir** masts and spars, **iron** guns, **elm** capstan, and ready for later **copper**, **canvas**, **hemp**, **stone**, **earth**.
- `damage_tile()` applies damage in oak-equivalents, so softer materials lose more. The ship view shades damaged planks and draws holes (`:`). The look cursor reports "pine planking, splintered (43%)".

**Next:** shot damage (Phase 2) resolves against these tiles and the people standing on them; splinters from oak hits wound nearby men; fire spreads by flammability; the carpenter repairs integrity; multiple decks get their own grids (the hull below the waterline is where leaks and flooding live).

## Items: every barrel recorded

- Items are entities: `Item` (kind, material, condition), `Contents` (goods and quantities, unit, capacity), and `Stowed` (which ship; a weather-deck tile, or below in the **hold** or **magazine**).
- `victual_ship()` loads stores from the complement and cruise length using **period ration scales** (per man per day: ~4.5 L water, 1 lb biscuit, salt beef and pork, peas, oatmeal, cheese, butter, **half a pint of rum** as grog) in period casks (butts, puncheons, hogsheads, barrels, bags, firkins). Powder barrels go in the magazine.
- On the weather deck where they really stood: a **shot garland** by each gun (12 rounds of the right calibre), the **scuttlebutt** of drinking water by the mainmast. They're drawn (`•`, `¤`) and reported by the look cursor.
- A sloop victualled for 60 days carries ~33,000 L of water, ~7,400 lb of biscuit, ~3,700 pints of rum and ~6,500 lb of powder, all as individual containers.

**Next:** consumption (the crew actually eats and drinks it; the grog ration draws on the rum), shot garlands emptied by firing and refilled from the shot lockers, spoilage, theft by thirsty men, resupply and prize cargo (Phase 5).

## Collision, fouling and boarding

- **Collision.** Each tick, ships close enough to touch are tested tile against tile in world space. Where hull tiles overlap, those planks on both ships take damage scaled by closing speed. Both ships lose their way, the faster is backed off until the hulls just touch, and both are marked **Fouled**. Fouled ships can't sail or turn until cut free.
- **Gangways.** Pairs of walkable deck tiles within ~3 m across the two rails, which men can climb between.
- **Boarding.** `ShipOrders.boarders_away` picks about half the hands on deck, best fighters first. They path to the nearest gangway and **step across**: the man's position leaves one ship's grid and lands on the other's (`CrewMember.ship` changes; `home_ship` remembers where he belongs, and his colour follows his home ship).
- **Defence.** When enemies are on a ship's deck, her idle hands turn out to fight.
- **Melee.** Each fighter swings every few seconds at an adjacent enemy. The hit chance comes from both men's **melee skill** and the attacker's **fear**. A hit wounds a weighted body part (`health.wound`): cuts bleed, severe ones break bones or carry away limbs, a blow to the head or neck can kill. Men collapse from blood loss and die. Their bodies stay where they fell (`%`).
- **Seeing it.** People are tested for visibility at **head height**, so you see heads and shoulders over an enemy's bulwark even when her deck planking is hidden. In planning mode you always see where your own men are, including boarders on the enemy's deck.

## Fortresses (planned)

A fortress is a **static structure** built exactly like a ship: a tile grid (stone and earth walls, gun platforms, magazines, barracks), a `StructureState`, a garrison of full people, stores, and guns on the same battery system. It sits on the generated coast at a fortified port. Because it goes through the same spatial query, the vision engine, gunnery and damage treat it like any other structure. It's slower to damage (stone and earth toughness) and it doesn't move. "A ship's a fool to fight a fort" should fall out of the numbers.

## Performance

A 74 carries ~590 people and ~2,500 item entities. The fleet scenario (twelve 74s and a frigate) holds ~23,700 entities, builds in ~1.4 s and simulates ~8× real time. Only people on deck pathfind, and only injured people get health ticks. Past a few fleets, **simulation level of detail** keeps the same data at lower update rates when far from the player: needs and psyche updated every minute rather than every second, and crews below decks resolved statistically until they matter. The data is never discarded.
