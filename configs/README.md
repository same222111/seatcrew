# Community configs

Shared SeatCrew profiles (`*.seatcrew.json`) that anyone can import with **Customize → Import…**.

## Contributing a config
1. In the app, open the workflow, go to **Customize**, choose your profile and click **Export / share → Download file**.
2. Put the file in `configs/<workflow>/` with a descriptive name, e.g. `configs/trading/conservative-low-turnover.seatcrew.json`.
3. Open a pull request saying what the profile is for and how you tested it.

Rules:
- Exports are stripped of API keys and secrets automatically. Still, check the file before you commit it. Never include keys, account numbers, personal paths or names you don't want public.
- Trading configs must stay **paper trading**. The app ignores broker settings in profiles anyway.
- Keep the `author` field to a handle you're happy to publish (or leave it empty).
