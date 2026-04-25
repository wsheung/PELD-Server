# PELD-Server

This is the codebase for the public site that sits at https://peld-fleet.com 

PELD-Server is the server component for the fleet networking feature of [PyEveLiveDPS (PELD)](https://github.com/ArtificialQualia/PyEveLiveDPS).  PELD-Server provides a webpage for FCs to use to do fleet management and gathering of combat stats from all of their fleet members running PELD.

This allows FCs to see what is happening to their fleet, and whom/what their fleet are attacking in realtime. This helps FCs decide on who to primary, to ensure fleet line members are engaging the correct targets, make sure logi chains are correct, etc.

## Deployment

If you wish to deploy your own version of this site, it is highly recommended to use Docker to deploy it rather than trying to do it yourself.  To read about how to do that, go [here](https://github.com/ArtificialQualia/PELD-Server/wiki/Deployment).  If you don't want to use Docker, glhf.

### Configuration

Before running, create a `.env` file in the project root with the following variables:

```
SERVER_NAME=your.domain.com
SECRET_KEY=<random hex string, e.g. from: python3 -c "import secrets; print(secrets.token_hex(32))">
ESI_CLIENT_ID=your_eve_sso_client_id
ESI_SECRET_KEY=your_eve_sso_secret_key
```

- **SERVER_NAME** — the hostname nginx will serve and where Let's Encrypt certificates are expected under `/etc/letsencrypt/live/<SERVER_NAME>/`
- **SECRET_KEY** — Flask session signing key; must be a strong random secret unique to your deployment
- **ESI_CLIENT_ID** / **ESI_SECRET_KEY** — credentials from your [EVE Online developer application](https://developers.eveonline.com/). Set the callback URL to `https://<SERVER_NAME>/sso/callback`

The `.env` file is gitignored and never committed — keep your credentials out of version control.

## Problems?  Feedback?

If you encounter any bugs or you think there are missing features please let me know [on the issues page](https://github.com/ArtificialQualia/PELD-Server/issues).

If you wish to contribute to the project codebase, I will be accepting pull requests.

If you love the website enough that you feel compelled to throw away ISK, donations are welcome to my eve character: **Demogorgon Asmodeous**

## Attributions

EVE Online, EVE logos, and all other EVE data are the intellectual property of CCP hf.