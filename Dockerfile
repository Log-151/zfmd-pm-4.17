ARG ODOO_IMAGE=odoo@sha256:f83602ecb7c5dfab85402bd10ece785bb2a883dd8e97e6884cacf4566dd4daa1
FROM ${ODOO_IMAGE}

USER root
RUN mkdir -p /opt/zfmd /mnt/extra-addons /etc/odoo

COPY addons /mnt/extra-addons
COPY odoo/odoo.conf /etc/odoo/odoo.conf
COPY odoo/odoo.prod.conf /etc/odoo/odoo.prod.conf
COPY deploy/start-odoo.sh /opt/zfmd/start-odoo.sh

RUN chown -R odoo:odoo /mnt/extra-addons /opt/zfmd /etc/odoo \
    && chmod +x /opt/zfmd/start-odoo.sh

USER odoo

EXPOSE 8069

ENTRYPOINT ["/opt/zfmd/start-odoo.sh"]
