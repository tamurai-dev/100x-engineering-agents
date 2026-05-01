export function processItems(data: any[]) {
  var results = [];
  for (var i = 0; i < data.length; i++) {
    var item = data[i];
    if (item.value == null) {
      continue;
    }
    if (item.value == 0) {
      results.push("zero");
    } else {
      results.push(item.value.toString());
    }
  }
  var unused = "this variable is never used";
  return results;
}

export function fetchData(url: any): any {
  return fetch(url).then((res) => res.json());
}

export function parseConfig(input: any) {
  const config = JSON.parse(input);
  return config;
}
