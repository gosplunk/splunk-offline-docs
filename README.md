# Splunk Offline Docs

Offline [help.splunk.com](https://help.splunk.com) browser Splunk app for air-gapped and restricted-network Splunk Enterprise deployments.

<p align="center">
  <img src="docs/images/hero-banner.png" alt="Splunk Offline Docs" width="720" />
</p>

**Author:** [Joe Hagan](mailto:joehaga@cisco.com)

## Download (air-gapped ready)

**Use the full release tarball** — it includes the pre-scraped documentation bundle (~19k topics). No internet access required to install or browse.

1. Go to **[Releases](https://github.com/gosplunk/splunk-offline-docs/releases)**
2. Download **`splunk_offline_docs_full.tgz`** from the latest release (v0.4.8+)
3. Install:

```bash
tar -xzf splunk_offline_docs_full.tgz -C $SPLUNK_HOME/etc/apps/
chown -R splunk:splunk $SPLUNK_HOME/etc/apps/splunk_offline_docs
$SPLUNK_HOME/bin/splunk restart
```

4. Open **Splunk Offline Docs** in Splunk Web.

> **Note:** The smaller `splunk_offline_docs.tgz` (app only, no docs) is for developers rebuilding from source. Air-gapped customers should always use `splunk_offline_docs_full.tgz`.

## What's included in the full release

| Product | help.splunk.com path |
|---------|----------------------|
| Splunk Enterprise | `splunk-enterprise` (latest 10.x) |
| Enterprise Security 8 | `splunk-enterprise-security-8` |
| SOAR (on-premises) | `splunk-soar/soar-on-premises` |
| IT Service Intelligence | `splunk-it-service-intelligence` |

~19,000 HTML topics, search index, navigation, and link resolution — ready offline on first install.

## Requirements

- Splunk Enterprise 9.x or later
- ~700 MB disk for the installed app with documentation bundle

## Updating documentation (optional)

If your Splunk server **can** reach help.splunk.com, admins can use the **Configuration** view:

- **Check now** — compare local versions against help.splunk.com
- **Incremental update** — fetch missing topics and repair links
- **Full refresh** — rebuild navigation and re-sync all products

Daily auto-check is **disabled by default** for air-gapped sites.

## Building from source (connected environments only)

For maintainers with outbound HTTPS to help.splunk.com:

```bash
git clone https://github.com/gosplunk/splunk-offline-docs.git
cd splunk-offline-docs
bash scripts/build_bundle.sh
bash scripts/package_release.sh
```

## App documentation

| Location | Audience |
|----------|----------|
| [splunk_offline_docs/README](splunk_offline_docs/README) | Splunk App Manager |
| **About** view in Splunk Web | All app users |
| **Configuration** view | Admins |

## Legal

- **App code** in this repository is licensed under the [Apache License 2.0](LICENSE).
- **Documentation HTML** mirrored from help.splunk.com is © Splunk Inc. Distributed for use with appropriately licensed Splunk deployments under Splunk's documentation terms for licensed customers.
- Splunk®, Splunk Enterprise®, and related marks are trademarks of Splunk Inc.

## Support

Contact [Joe Hagan](mailto:joehaga@cisco.com).
