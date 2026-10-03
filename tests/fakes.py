from everlock.mailer import Mailer, MailError


class RecordingMailer(Mailer):
    """Guarda as mensagens em memória: nenhum teste envia e-mail de verdade."""

    def __init__(self, fail=False):
        super().__init__(None, "http://127.0.0.1:8000")
        self.outbox, self.resets, self.fail = [], [], fail

    def send_confirmation(self, to, username, token):
        if self.fail:
            raise MailError("SMTPException")
        self.outbox.append({"to": to, "username": username, "token": token})
        return "email"


class FakeFaceEngine:
    """Motor facial de mentira: o conteúdo da "imagem" diz quem aparece nela.

    PESSOA:<nome>:<n>[:<giro>]   rosto da pessoa; <n> muda só um pouco o vetor (outra foto);
                                 <giro> é o yaw (0 = de frente; + = vira à esquerda da pessoa).
    MISTURA:<a>:<b>:<n>          rosto parecido com duas pessoas ao mesmo tempo.
    SEMROSTO / DOISROSTOS / BORRADO   falhas de captura.
    """

    available, reason, model_id = True, "", "falso"

    @staticmethod
    def _unit(seed, size=128):
        import math
        import random

        generator = random.Random(seed)
        values = [generator.gauss(0, 1) for _ in range(size)]
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]

    def read(self, image):
        from everlock.faces import FaceError, FaceReading

        text = image.decode(errors="ignore")
        failures = {
            "SEMROSTO": ("no_face", "Nenhum rosto foi encontrado."),
            "DOISROSTOS": ("multiple_faces", "Há mais de um rosto na imagem."),
            "BORRADO": ("blurry", "A imagem está tremida."),
        }
        if text in failures:
            raise FaceError(*failures[text])
        parts = text.split(":")
        yaw = float(parts[3]) if parts[0] == "PESSOA" and len(parts) == 4 else 0.0
        if parts[0] == "PESSOA" and len(parts) in (3, 4):
            base = self._unit(f"base:{parts[1]}")
        elif parts[0] == "MISTURA" and len(parts) == 4:
            first, second = self._unit(f"base:{parts[1]}"), self._unit(f"base:{parts[2]}")
            base = [a + b for a, b in zip(first, second, strict=True)]
        else:
            raise FaceError("invalid_image", "Não foi possível ler a imagem enviada.")
        noise = self._unit(f"ruido:{text}")
        vector = tuple(a + 0.1 * b for a, b in zip(base, noise, strict=True))
        return FaceReading(vector, 160, 0.99, 100.0, yaw)


def _send_reset(self, to, username, token):
    if self.fail:
        raise MailError("SMTPException")
    self.resets.append({"to": to, "username": username, "token": token})
    return "email"


RecordingMailer.send_reset = _send_reset
