function api_post(url, data) {
  const body = JSON.stringify(data);
  return fetch(url, {
    credentials: "same-origin",
    mode: "same-origin",
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: body
  }).then((resp) => {
    if(resp.redirected)
      window.location.href = resp.url;

    if(resp.headers.get('content-type') !== "application/json") {
      throw resp;
    }

    return resp.json().then(res => {
      if (res.hasOwnProperty('error')) {
        throw res['error'];
      } else if(res.hasOwnProperty('errors')) {
        let errors = JSON.parse(res['errors']);
        let rtns = [];

        errors.forEach(el => {
          rtns.push(`${el.loc}: ${el.msg}`);
        });

        throw rtns;
      }

      return res;
    });
  });
}
