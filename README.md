# Nextcloud
The self-hosted productivity platform that keeps you in control of your data.

Works with postgresql as a database backend.

## Description
The full documentation for this charm lives here: https://charmhub.io/nextcloud/docs

## Small scale deployment
For a quick test of nextcloud, you can use this:

    juju add-model my-nextcloud
    juju model-config default-series=jammy
    juju deploy postgresql
    juju deploy nextcloud
    juju integrate nextcloud:database postgresql

    ... wait for deployment to settle.
    Then, visit http://ip.ip.ip.ip

To get the admin password:

    juju run nextcloud/0 get-admin-password --wait

Make sure to note it and change it after first login, since this action will only work once.

## Large scale deployment
For a full scale out deployment with support for shared storage, redis and SSL deployment, see: https://charmhub.io/nextcloud/docs

## Supported deployment
The authors of this charm provides fully supported, large scale [Nextcloud] installations in collaboration with [Kafit.se] 
under a official partner program with [Nextcloud].

Contact [Kafit.se] or [Erik Lönroth] for more information on professional supported solutions of Nextcloud. 

Any installation growing above 100 users should consider a enterprise license contract

## Contribute to this charm
We love to see more people adding to the charm code. Let us know if you want to help develop it.

https://github.com/nextcloud-charmers/nextcloud-charms

## Authors/Developers
Some of the developers...

[Erik Lönroth]

Joakim Nyman

Heitor Bittencourt

## Attributions
[Kafit.se] - Experts in Nextcloud and provides competence services. A partner with [Nextcloud] Ltd.
[Nextcloud] - Develops and supports the community of Nextcloud.

[Nextcloud]: https://nextcloud.com/
[Kafit.se]: https://kafit.se/?lang=en
[Erik Lönroth]: https://eriklonroth.com

Canonical - for Juju!
