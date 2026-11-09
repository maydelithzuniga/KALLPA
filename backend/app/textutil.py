def pluralize(word: str) -> str:
    out = []
    for w in word.split():
        if w[-1] in "aeiouáéó":
            out.append(w + "s")
        elif w[-1] == "z":
            out.append(w[:-1] + "ces")
        elif w[-1] == "s":
            out.append(w)
        elif w[-1] not in "lnrdjy":
            out.append(w + "s")
        else:
            # agudas con tilde pierden la tilde al pluralizar: limón → limones, melón → melones
            if len(w) > 2 and w[-2] in "áéíóú":
                w = w[:-2] + "aeiou"["áéíóú".index(w[-2])] + w[-1]
            out.append(w + "es")
    return " ".join(out)


def weekday_plural(name: str) -> str:
    return name + "s" if name in ("sábado", "domingo") else name
