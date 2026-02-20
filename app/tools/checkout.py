import logging
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

_BOOKING_URLS: dict[str, str] = {
    # Trains
    "KTX": "https://www.letskorail.com/ebizbf/EbizBfTicketSearch.do",
    "KTX-산천": "https://www.letskorail.com/ebizbf/EbizBfTicketSearch.do",
    "SRT": "https://etk.srail.kr/hpg/hra/01/selectScheduleList.do",
    "무궁화호": "https://www.letskorail.com/ebizbf/EbizBfTicketSearch.do",
    # Flights
    "대한항공": "https://www.koreanair.com/booking/search",
    "아시아나항공": "https://flyasiana.com/C/KR/KO/booking",
    "진에어": "https://www.jinair.com/booking/index",
    "제주항공": "https://www.jejuair.net/ko/main/booking",
    "티웨이항공": "https://www.twayair.com/booking/search",
    "에어부산": "https://www.airbusan.com/booking/search",
    # Buses
    "고속버스 우등": "https://www.kobus.co.kr/mrs/rotinf.do",
    "고속버스 프리미엄": "https://www.kobus.co.kr/mrs/rotinf.do",
    "고속버스 일반": "https://www.kobus.co.kr/mrs/rotinf.do",
    "시외버스": "https://www.bustago.or.kr/newweb/search",
}

_CHECKOUT_EXPIRY_MINUTES = 30


async def get_checkout_link(option: TransitOption) -> dict:
    """Generate a checkout/booking link for the given transit option.

    Returns a dict with:
        - checkout_url: a realistic booking URL for the provider
        - expires_at: ISO-format datetime string, 30 minutes from now
    """
    try:
        base_url = _BOOKING_URLS.get(option.provider, _default_url(option.transport_type))
        booking_ref = uuid.uuid4().hex[:12]
        dep_str = option.departure_time.strftime("%Y%m%dT%H%M")
        checkout_url = f"{base_url}?ref={booking_ref}&dep={quote(dep_str)}"

        expires_at = datetime.utcnow() + timedelta(minutes=_CHECKOUT_EXPIRY_MINUTES)

        return {
            "checkout_url": checkout_url,
            "expires_at": expires_at.isoformat(),
        }

    except Exception:
        logger.exception("get_checkout_link failed")
        return {
            "checkout_url": "",
            "expires_at": "",
        }


def _default_url(transport_type: TransportType) -> str:
    defaults = {
        TransportType.train: "https://www.letskorail.com/ebizbf/EbizBfTicketSearch.do",
        TransportType.flight: "https://www.koreanair.com/booking/search",
        TransportType.bus: "https://www.kobus.co.kr/mrs/rotinf.do",
    }
    return defaults.get(transport_type, "https://www.kobus.co.kr/mrs/rotinf.do")
