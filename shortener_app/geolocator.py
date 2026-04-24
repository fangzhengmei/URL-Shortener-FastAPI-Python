# geolocator.py
# IP geolocation functionality

import json
import logging
from functools import lru_cache
from typing import Dict, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import get_settings

logger = logging.getLogger(__name__)


class IPGeolocator:
    def __init__(self, timeout: float = 2.0, max_cache_size: int = 1000):
        self.timeout = timeout
        self.max_cache_size = max_cache_size
        self._cached_lookup = lru_cache(maxsize=max_cache_size)(self._lookup_ip)

    def _lookup_ip(self, ip_address: str) -> Optional[Dict]:
        if not ip_address or self._is_private_ip(ip_address):
            return None

        try:
            settings = get_settings()
            if hasattr(settings, 'geolocation_provider') and settings.geolocation_provider == 'none':
                return None
        except:
            pass

        url = f"http://ip-api.com/json/{ip_address}?fields=country,countryCode,region,regionName,city,status,message"
        
        try:
            req = Request(url, headers={'User-Agent': 'URL-Shortener-FastAPI/1.0'})
            with urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if data.get('status') == 'success':
                    return {
                        'country': data.get('country', ''),
                        'country_code': data.get('countryCode', ''),
                        'region': data.get('regionName', ''),
                        'region_code': data.get('region', ''),
                        'city': data.get('city', '')
                    }
                else:
                    logger.warning(f"IP geolocation failed for {ip_address}: {data.get('message', 'unknown error')}")
                    return None
                    
        except URLError as e:
            logger.warning(f"Network error during IP geolocation for {ip_address}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse geolocation response for {ip_address}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error during IP geolocation for {ip_address}: {e}")
            return None

    def _is_private_ip(self, ip_address: str) -> bool:
        ip = ip_address.strip()
        
        if ip.startswith('127.') or ip == '::1' or ip == 'localhost':
            return True
        
        if ip.startswith('10.'):
            return True
        
        if ip.startswith('172.'):
            try:
                parts = ip.split('.')
                if len(parts) >= 2:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        return True
            except:
                pass
        
        if ip.startswith('192.168.'):
            return True
        
        if ip.startswith('fc') or ip.startswith('fd') or ip.startswith('fe80:'):
            return True
        
        return False

    def lookup(self, ip_address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not ip_address:
            return (None, None, None)
        
        result = self._cached_lookup(ip_address)
        
        if result:
            return (
                result.get('country'),
                result.get('region'),
                result.get('city')
            )
        
        return (None, None, None)

    def clear_cache(self):
        self._cached_lookup.cache_clear()

    def cache_info(self):
        return self._cached_lookup.cache_info()


_geolocator_instance: Optional[IPGeolocator] = None


def get_geolocator() -> IPGeolocator:
    global _geolocator_instance
    if _geolocator_instance is None:
        _geolocator_instance = IPGeolocator()
    return _geolocator_instance


def get_geolocation(ip_address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return get_geolocator().lookup(ip_address)
