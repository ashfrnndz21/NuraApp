/** A small key-value store on IndexedDB: the token, the chosen profile, the language, the
 *  density, and the last Today page. IndexedDB because it outlives the tab, is available to
 *  a home-screen app on iOS, and is never sent to the server (a cookie would be, on every
 *  request, to routes that do not want it). Where IndexedDB is missing the store is a Map,
 *  which is what a unit test sees. */

const DB = "nura";
const STORE = "kv";

const memory = new Map<string, unknown>();

function hasIndexedDb(): boolean {
  return typeof indexedDB !== "undefined";
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Run one request in its own transaction and settle when the transaction has committed —
 *  not when the request succeeded — so a write awaited here is on disk before the page can
 *  reload or the app can be closed. */
function run<T>(mode: IDBTransactionMode, act: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const request = act(tx.objectStore(STORE));
        tx.oncomplete = () => {
          db.close();
          resolve(request.result);
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error);
        };
        tx.onabort = () => {
          db.close();
          reject(tx.error);
        };
      }),
  );
}

export async function kvGet<T>(key: string): Promise<T | undefined> {
  if (!hasIndexedDb()) return memory.get(key) as T | undefined;
  try {
    return (await run<unknown>("readonly", (store) => store.get(key))) as T | undefined;
  } catch {
    return memory.get(key) as T | undefined;
  }
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  memory.set(key, value);
  if (!hasIndexedDb()) return;
  try {
    await run("readwrite", (store) => store.put(value, key));
  } catch {
    /* the in-memory copy stands for this session */
  }
}

export async function kvDel(key: string): Promise<void> {
  memory.delete(key);
  if (!hasIndexedDb()) return;
  try {
    await run("readwrite", (store) => store.delete(key));
  } catch {
    /* nothing to forget */
  }
}
