import re
from quart import g, jsonify, request
from http import HTTPStatus

from lnbits.core.crud import get_user, get_wallet
from lnbits.core.services import create_invoice, check_invoice_status
from lnbits.decorators import api_check_wallet_key, api_validate_post_request

from . import subdomains_ext
from .crud import (
    create_subdomain,
    set_subdomain_paid,
    get_subdomain,
    get_subdomains,
    delete_subdomain,
    create_domain,
    update_domain,
    get_domain,
    get_domains,
    delete_domain,
)


# domainS


@subdomains_ext.route("/api/v1/domains", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_domains():
    wallet_ids = [g.wallet.id]

    if "all_wallets" in request.args:
        wallet_ids = (await get_user(g.wallet.user)).wallet_ids

    return jsonify([domain._asdict() for domain in await get_domains(wallet_ids)]), HTTPStatus.OK


@subdomains_ext.route("/api/v1/domains", methods=["POST"])
@subdomains_ext.route("/api/v1/domains/<domain_id>", methods=["PUT"])
@api_check_wallet_key("invoice")
@api_validate_post_request(
    schema={
        "wallet": {"type": "string", "empty": False, "required": True},
        "domain": {"type": "string", "empty": False, "required": True},
        "cfToken": {"type": "string", "empty": False, "required": True},
        "cfZoneId": {"type": "string", "empty": False, "required": True},
        "webhook": {"type": "string", "empty": False, "required": False},
        "description": {"type": "string", "min": 0, "required": True},
        "cost": {"type": "integer", "min": 0, "required": True},
    }
)
async def api_domain_create(domain_id=None):
    if domain_id:
        domain = await get_domain(domain_id)

        if not domain:
            return jsonify({"message": "domain does not exist."}), HTTPStatus.NOT_FOUND

        if domain.wallet != g.wallet.id:
            return jsonify({"message": "Not your domain."}), HTTPStatus.FORBIDDEN

        domain = await update_domain(domain_id, **g.data)
    else:
        domain = await create_domain(**g.data)
    return jsonify(domain._asdict()), HTTPStatus.CREATED


@subdomains_ext.route("/api/v1/domains/<domain_id>", methods=["DELETE"])
@api_check_wallet_key("invoice")
async def api_domain_delete(domain_id):
    domain = await get_domain(domain_id)

    if not domain:
        return jsonify({"message": "domain does not exist."}), HTTPStatus.NOT_FOUND

    if domain.wallet != g.wallet.id:
        return jsonify({"message": "Not your domain."}), HTTPStatus.FORBIDDEN

    await delete_domain(domain_id)

    return "", HTTPStatus.NO_CONTENT


#########subdomains##########


@subdomains_ext.route("/api/v1/subdomains", methods=["GET"])
@api_check_wallet_key("invoice")
async def api_subdomains():
    wallet_ids = [g.wallet.id]

    if "all_wallets" in request.args:
        wallet_ids = (await get_user(g.wallet.user)).wallet_ids

    return jsonify([domain._asdict() for domain in await get_subdomains(wallet_ids)]), HTTPStatus.OK


@subdomains_ext.route("/api/v1/subdomains/<domain_id>", methods=["POST"])
@api_validate_post_request(
    schema={
        "domain": {"type": "string", "empty": False, "required": True},
        "subdomain": {"type": "string", "empty": False, "required": True},
        "email": {"type": "string", "empty": True, "required": True},
        "ip": {"type": "string", "empty": False, "required": True},
        "sats": {"type": "integer", "min": 0, "required": True},
    }
)
async def api_subdomain_make_subdomain(domain_id):
    domain = await get_domain(domain_id)
    if not domain:
        return jsonify({"message": "LNsubdomain does not exist."}), HTTPStatus.NOT_FOUND

    subdomain = len(re.split(r"\s+", g.data["subdomain"]))
    sats = g.data["sats"]
    payment_hash, payment_request = await create_invoice(
        wallet_id=domain.wallet,
        amount=sats,
        memo=f"subdomain with {subdomain} words on {domain_id}",
        extra={"tag": "lnsubdomain"},
    )

    subdomain = await create_subdomain(payment_hash=payment_hash, wallet=domain.wallet, **g.data)

    if not subdomain:
        return jsonify({"message": "LNsubdomain could not be fetched."}), HTTPStatus.NOT_FOUND

    return jsonify({"payment_hash": payment_hash, "payment_request": payment_request}), HTTPStatus.OK


@subdomains_ext.route("/api/v1/subdomains/<payment_hash>", methods=["GET"])
async def api_subdomain_send_subdomain(payment_hash):
    subdomain = await get_subdomain(payment_hash)
    try:
        status = await check_invoice_status(subdomain.wallet, payment_hash)
        is_paid = not status.pending
    except Exception:
        return jsonify({"paid": False}), HTTPStatus.OK

    if is_paid:
        wallet = await get_wallet(subdomain.wallet)
        payment = await wallet.get_payment(payment_hash)
        await payment.set_pending(False)
        subdomain = await set_subdomain_paid(payment_hash=payment_hash)
        return jsonify({"paid": True}), HTTPStatus.OK

    return jsonify({"paid": False}), HTTPStatus.OK


@subdomains_ext.route("/api/v1/subdomains/<subdomain_id>", methods=["DELETE"])
@api_check_wallet_key("invoice")
async def api_subdomain_delete(subdomain_id):
    subdomain = await get_subdomain(subdomain_id)

    if not subdomain:
        return jsonify({"message": "Paywall does not exist."}), HTTPStatus.NOT_FOUND

    if subdomain.wallet != g.wallet.id:
        return jsonify({"message": "Not your subdomain."}), HTTPStatus.FORBIDDEN

    await delete_subdomain(subdomain_id)

    return "", HTTPStatus.NO_CONTENT
