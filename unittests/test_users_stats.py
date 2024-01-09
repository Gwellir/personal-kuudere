from unittest import TestCase

from handler_modules.users_stats import UsersStats
from orm.ORMWrapper import BaseRelations

br = BaseRelations()
us = UsersStats()


class TestUsersStats(TestCase):
    def test_process(self):
        res = us.process(["season"])
        print(res)
        self.assertEqual(
            res,
            """Активные пользователи:
DarkElve
Valion
Jim_Di
Rasifiel
Himura_Yumi
ArdRaeiss
toiro
amauros
unambo
deltax_msc
Stalok
Serusha""",
        )
        res = us.process([])
        print(res)
        self.assertEqual(
            res,
            """Список пользователей:
DarkElve - DarkElve
rune_s - Rune_Sa_Riik
Valion - Valion
Hwestar - Hwestar
rn144mg - rn144mg
Jim_Di - Jim_Di
Odiumag - Odium
Rasifiel - Rasifiel
baka_utena - Utena
Himura_Yumi - Himura_Yumi
None - wi_ma
oslikdixon - SleepKp0t
ambtech - toiro
Magistr - u3m
Erufu_Wizarudo - Erufu_Wizardo
Al_pixel - al_pixel
maurus - amauros
Simak2001 - Simakov_Ilja
molotoko - Molotoko
deltax - deltax_msc
beavered - beavered
ylguam - maugly
ArdRaeiss - ArdRaeiss
unambo - unambo
Otakon273 - Otakon273
Lacki23 - Lacki23
Serusha - Serusha
Stalok - Stalok""",
        )
