import abc

from handler_modules.image_extractor.models import PostData


class BaseScraper(abc.ABC):
    @abc.abstractmethod
    def scrape(self, url: str) -> PostData:
        pass
