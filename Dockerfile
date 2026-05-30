FROM odoo:17

USER root
RUN mkdir -p /opt/zfmd /mnt/extra-addons /etc/odoo

COPY addons /mnt/extra-addons
COPY odoo/odoo.conf /etc/odoo/odoo.conf
COPY deploy/start-odoo.sh /opt/zfmd/start-odoo.sh

RUN chown -R odoo:odoo /mnt/extra-addons /opt/zfmd /etc/odoo \
    && chmod +x /opt/zfmd/start-odoo.sh

USER odoo

EXPOSE 8069

ENTRYPOINT ["/opt/zfmd/start-odoo.sh"]
