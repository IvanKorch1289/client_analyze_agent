def clean_xml_dict(data):
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            new_key = key
            if isinstance(key, str):
                new_key = key.lstrip("@#")
            cleaned[new_key] = clean_xml_dict(value)
        return cleaned
    elif isinstance(data, list):
        return [clean_xml_dict(item) for item in data]
    else:
        return data
