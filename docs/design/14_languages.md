# Generated Languages and Names

Every people in the world speaks a language generated from the world seed. Nothing is named after a real people, place or language: names are invented words in invented tongues, and — as in Dwarf Fortress — they *mean* something, so a name can be translated. Code: `sim/people/language.py`, `sim/people/cultures.py`.

## Why generated rather than borrowed

Earlier drafts labelled cultures "Iberian", "Gallic", "Hellenic" and so on. The flavour worked but the words point straight at the real world, which fights the fiction. Generated languages give the same familiar-but-unplaceable feel without borrowing a real identity.

## How a language is made

1. **Flavours (raw material, never shown).** Twelve sound systems — inspired by Latin, Welsh, Esperanto, Slavic, Germanic, Greek, Nahuatl, Finnish, Swahili, Quechua, Japanese and Turkish — each defined as weighted inventories of onsets, vowels and codas, plus syllable shapes, typical word length, name endings and whether a modifier goes before or after its noun.
2. **Blending.** A language picks one or (usually) two flavours and merges their inventories with a random weighting, so it lands between two sound worlds rather than on either.
3. **Mutation.** It drops a random slice of the inherited sounds, and adopts a **signature** spelling habit of its own (`kh`, `ll`, `rr`, `'`, `ö`, `é`, `zh`...) which surfaces in perhaps a quarter of its words.
4. **Lexicon.** English concepts — *salt, stone, bay, wolf, iron, thunder, people, son, land* — map to words in that language, generated deterministically on first use. The same seed always produces the same lexicon.

## Names as meaning

- **Family names** are compounds of two concepts, or "child of" forms: *Puquir* ("Wind-Wolf"), *Naimoönend* ("child of Moönend").
- **Place names** compound a modifier with a place word, in the language's own word order: *Xiyawiqzik* ("Stoneshore"), *Bastwiri* ("Highrock"), *Ffung Meön* ("Red Bay").
- **Ship names** come from a martial vocabulary: *Chutltlinakan* ("Swift Wrath"), *Ryminä* ("Iron Serpent").
- **A people's own name** is its word for "people": the Kiwun, the Zötuqi, the Githösi. The demonym adds an English-side adjectival ending so it reads naturally in text ("a Githösi seaman").
- **Nations** take a land name plus a government drawn from a generic list (kingdom, merchant republic, league of free cities, grand despotate...).

Every generated name keeps its translation, so the interface can show *Varnakkel ("Saltbay")* wherever that's useful — a natural fit for the look cursor and a future crew roster.

## Filtering

Generated words are rejected when they collide with real English words that would jar or offend, and when they're too short to read as a name.

## Where languages are used

- **Default peoples (k0–k8)** for hand-built scenarios: nine fixed languages, so scenario crews are stable between runs. Faction labels in scenario code (`"british"`, `"french"`) are internal handles only; the people, their names and their speech are fictional.
- **A generated world** makes one people per region plus one for the outside sea power, registered under the world's seed. Ports, nations, admirals, ships and every sailor's name come from them.
- **Crews are mixed**: roughly 70% of a ship's company come from her own nation's people and 30% from others, as period warship crews really were.

## Next steps

- **Language families:** generate a proto-language and derive daughters by sound shifts, so neighbouring peoples' languages are visibly related and distant ones aren't.
- **Dialect and register:** different name pools for gentry and lower deck, and for different regions of one nation.
- **Words in play:** ships' names, signals and sworn oaths in the language, with translations on hover; a captain who doesn't speak a prisoner's tongue needs an interpreter.
- **Writing:** the chronicle in the local language with English glosses.
