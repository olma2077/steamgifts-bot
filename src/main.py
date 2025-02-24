import sys
import configparser
import requests
import json
import asyncio

from random import randint
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed
from bs4 import BeautifulSoup

from cli import log


class SteamGifts:
    def __init__(self, cookie, gifts_type, pinned, min_points):
        self.cookie = {
            'PHPSESSID': cookie
        }
        self.gifts_type = gifts_type
        self.pinned = pinned
        self.min_points = int(min_points)

        self.base = "https://www.steamgifts.com"
        self.session = None

        self.filter_url = {
            'All': "search?page=%d",
            'Wishlist': "search?page=%d&type=wishlist",
            'Recommended': "search?page=%d&type=recommended",
            'Copies': "search?page=%d&copy_min=2",
            'DLC': "search?page=%d&dlc=true",
            'Group': "search?page=%d&type=group",
            'New': "search?page=%d&type=new"
        }

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(1))
    async def get_soup_from_page(self, url):
        async with self.session.get(url) as r:
            soup = BeautifulSoup(await r.text(), 'html.parser')
        return soup

    async def update_info(self):
        soup = await self.get_soup_from_page(self.base)

        try:
            self.xsrf_token = soup.find('input', {'name': 'xsrf_token'})['value']
            self.points = int(soup.find('span', {'class': 'nav__points'}).text)  # storage points
        except TypeError:
            log("⛔  Cookie is not valid.", "red")
            asyncio.sleep(10)
            exit()

    async def get_game_content(self, page=1):
        n = page

        while True:
            txt = "⚙️  Retrieving %s games from page %d." % (self.gifts_type, n)
            log(txt, "magenta")

            filtered_url = self.filter_url[self.gifts_type] % n
            paginated_url = f"{self.base}/giveaways/{filtered_url}"

            soup = await self.get_soup_from_page(paginated_url)

            pinned = soup.find('div', {'class': 'pinned-giveaways__outer-wrap'})

            game_list = []
            if self.pinned:
                game_list = pinned.find_all('div', {'class': 'giveaway__row-inner-wrap'})

            common_sections = pinned.find_next_siblings()
            common_list = []
            for item in common_sections:
                common_list += item.find_all('div', {'class': 'giveaway__row-inner-wrap'})

            if not len(common_list):
                break

            game_list += common_list

            for item in game_list:
                if 'is-faded' in item['class']:
                    continue

                if self.points == 0 or self.points < self.min_points:
                    txt = f"🛋️  Sleeping to get 6 points. We have {self.points} points, but we need {self.min_points} to start."
                    log(txt, "yellow")
                    await asyncio.sleep(900)
                    await self.start()
                    break

                game_cost = item.find_all('span', {'class': 'giveaway__heading__thin'})[-1]

                if game_cost:
                    game_cost = game_cost.getText().replace('(', '').replace(')', '').replace('P', '')
                else:
                    continue

                game_name = item.find('a', {'class': 'giveaway__heading__name'}).text

                if self.points - int(game_cost) < 0:
                    txt = f"⛔ Not enough points to enter {self.gifts_type}: {game_name}"
                    log(txt, "red")
                    continue

                elif self.points - int(game_cost) >= 0:
                    game_id = item.find('a', {'class': 'giveaway__heading__name'})['href'].split('/')[2]
                    res = await self.entry_gift(game_id)
                    if res:
                        self.points -= int(game_cost)
                        txt = f"🎉 One more {self.gifts_type} game! Has just entered {game_name}"
                        log(txt, "green")
                        await asyncio.sleep(randint(3, 7))

            n = n+1


        log(f"🛋️  List of {self.gifts_type} games is ended. Waiting 15 mins to update...", "yellow")
        await asyncio.sleep(900)
        await self.start()

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(1))
    async def entry_gift(self, game_id):
        payload = {'xsrf_token': self.xsrf_token, 'do': 'entry_insert', 'code': game_id}
        entry = await self.session.post('https://www.steamgifts.com/ajax.php', data=payload)
        json_data = json.loads(await entry.text())

        if json_data['type'] == 'success':
            return True

    async def start(self):
        if not self.session:
            self.session = aiohttp.ClientSession(cookies=self.cookie)

        await self.update_info()

        if self.points > 0:
            txt = "🤖 Hoho! I am back! You have %d points. Lets hack some %s games." % (self.points, self.gifts_type)
            log(txt, "blue")

        await self.get_game_content()
