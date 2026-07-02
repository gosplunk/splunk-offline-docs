# Splunk Offline Docs

Offline [help.splunk.com](https://help.splunk.com) browser Splunk app for on-premises products. Built for air-gapped and restricted-network Splunk Enterprise deployments.

![Splunk Offline Docs](splunk_offline_docs/appserver/static/images/screenshot.png)

**Author:** [Joe Hagan](mailto:joehaga@cisco.com)

## Download

### Option A — GitHub Release (app package)

Download the latest `splunk_offline_docs.tgz` from the [Releases](https://github.com/gosplunk/splunk-offline-docs/releases) page. This tarball contains the Splunk app and scraper tooling. You still need to **build or import the documentation bundle** (see below) before browsing offline help.

### Option B — Clone and build

```bash
git clone https://github.com/gosplunk/splunk-offline-docs.git
cd splunk-offline-docs
bash scripts/build_bundle.sh
bash scripts/package.sh
```

The build script downloads documentation from help.splunk.com (requires outbound HTTPS during build).

## Products in the bundle

| Product | help.splunk.com path |
|---------|----------------------|
| Splunk Enterprise | `splunk-enterprise` (latest 10.x) |
| Enterprise Security 8 | `splunk-enterprise-security-8` |
| SOAR (on-premises) | `splunk-soar/soar-on-premises` |
| IT Service Intelligence | `splunk-it-service-intelligence` |

Cloud-only and other help trees are not included by default. Extend `scraper/products.yaml` and rebuild to add more.

## Install on Splunk Enterprise

```bash
tar -xzf splunk_offline_docs.tgz -C $SPLUNK_HOME/etc/apps/
chown -R splunk:splunk $SPLUNK_HOME/etc/apps/splunk_offline_docs
$SPLUNK_HOME/bin/splunk restart
```

Open **Splunk Offline Docs** in Splunk Web navigation.

If you built from source, install from `artifacts/splunk_offline_docs.tgz` after `scripts/package.sh`.

## Requirements

- Splunk Enterprise 9.x or later
- ~700 MB–1 GB disk for the documentation bundle
- Python 3.9+ with packages in `scraper/requirements.txt` (build/update host only)
- Outbound HTTPS to help.splunk.com during bundle build or in-app updates

## App documentation

| Location | Audience |
|----------|----------|
| [splunk_offline_docs/README](splunk_offline_docs/README) | Splunk App Manager |
| **About** view in Splunk Web | All app users |
| **Configuration** view | Admins — bundle metrics, updates, daily check |

## Build pipeline

```bash
# Full scrape + package
bash scripts/build_bundle.sh
bash scripts/package.sh

# Incremental sync (after initial build)
bash scripts/sync_content.sh
bash scripts/package.sh
```

Monitor a full build:

```bash
tail -f artifacts/build.log
```

## Updating on an installed instance

Admins can use the **Configuration** view in Splunk Web:

- **Check now** — compare local versions against help.splunk.com
- **Incremental update** — fetch missing topics and repair links
- **Full refresh** — rebuild navigation and re-sync all products

Daily auto-check is **disabled by default** for air-gapped sites.

## Legal

- **App code** in this repository is licensed under the [Apache License 2.0](LICENSE).
- **Documentation HTML** mirrored from help.splunk.com is © Splunk Inc. Use only with appropriately licensed Splunk deployments, in accordance with your Splunk license and Splunk's documentation terms.
- Splunk®, Splunk Enterprise®, and related marks are trademarks of Splunk Inc.

## Support

For questions about this app, contact [Joe Hagan](mailto:joehaga@cisco.com).

For product documentation accuracy, refer to [help.splunk.com](https://help.splunk.com) when online.
