from time import sleep

import requests

from handler_modules.base import Handler
from handler_modules.voting_system.exceptions import MalformedABParamsError
from orm.ORMWrapper import VotedCharacters


class VotingUpload(Handler):
    command = "voting_upload"

    def parse(self, args):
        id_str, ab_sess, _auth = tuple(args)
        bracket_id = int(id_str)
        if len(ab_sess) != 64 or len(_auth) != 16:
            raise MalformedABParamsError

        return bracket_id, ab_sess, _auth

    def process(self, params):
        bracket_id, ab_sess, _auth = params
        session = self.br.get_session()
        candidates = list(
            session.query(VotedCharacters).filter_by(is_posted=False).all()
        )
        errors = []
        if candidates:
            url = "https://animebracket.com/submit/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 OPR/73.0.3856.284"
            }
            cookies = {
                "AB_SESS": ab_sess,
            }
            params = {"action": "nominate"}
            for entry in candidates:
                data = {
                    "nomineeName": entry.name,
                    "nomineeSource": entry.title,
                    "image": entry.image_url,
                    "bracketId": bracket_id,
                    "_auth": _auth,
                }
                q = requests.post(
                    url, cookies=cookies, headers=headers, data=data, params=params
                )
                if q.text == '{"success":true}':
                    entry.is_posted = True
                elif (
                    q.text
                    == '{"success":false,"message":"You\'re doing that too fast!"}'
                ):
                    sleep(2)
                    candidates.append(entry)
                else:
                    errors.append(f'{entry.name}: "{q.text}"')
                sleep(2)
            session.commit()

        session.close()

        err_text = "\n".join(errors)
        return f"posted everything but:\n\n{err_text}"
