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
            out.append(w + "es")
    return " ".join(out)


def weekday_plural(name: str) -> str:
    return name + "s" if name in ("sábado", "domingo") else name
