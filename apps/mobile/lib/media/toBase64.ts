/**
 * A local file/blob URI (from `expo-document-picker`, which returns a
 * URI but no base64) to a base64 string — via `fetch` + `FileReader`,
 * both already available (RN's built-in `fetch` returns a `Blob` for a
 * `file://`/`content://` URI same as it does on web), so this needs no
 * extra dependency beyond `expo-document-picker` itself.
 */
export function uriToBase64(uri: string): Promise<string> {
  return fetch(uri)
    .then((res) => res.blob())
    .then(
      (blob) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(reader.error ?? new Error('could not read file'));
          reader.onloadend = () => {
            const result = reader.result;
            if (typeof result !== 'string') {
              reject(new Error('unexpected FileReader result'));
              return;
            }
            // "data:<mime>;base64,<data>" — only the part after the comma is base64.
            const comma = result.indexOf(',');
            resolve(comma >= 0 ? result.slice(comma + 1) : result);
          };
          reader.readAsDataURL(blob);
        }),
    );
}
