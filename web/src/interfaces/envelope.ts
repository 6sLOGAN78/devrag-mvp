/** The single response envelope used by both engines (D-13). */
export interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
