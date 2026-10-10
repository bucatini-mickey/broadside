# One module per simulated process. Each system is a plain function
# (or small set of functions) taking the esper.World (and whatever else it
# needs - clock, rng, event bus) and mutating components. No classes with
# hidden state beyond what a future field/grid genuinely needs to persist
# between ticks (e.g. WindField below) - keep systems easy to reason about
# and easy to unit test headless.
