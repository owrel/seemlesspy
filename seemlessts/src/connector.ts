import type { Contract, ContractResolution, ContractUpdate } from "./contract";

interface Pending {
    resolve: (result: unknown) => void;
    reject: (error: Error) => void;
}

export const DEFAULT_URL = "ws://127.0.0.1:8000/ws";

export interface ConnectorOptions {
    url?: string;
}

export class Connector {
    private socket: WebSocket | null = null;
    private connecting: Promise<void> | null = null;
    private pending: Pending[] = [];
    private updates = new Set<(update: ContractUpdate) => void>();

    constructor(public url: string = DEFAULT_URL) {}

    connect(): Promise<void> {
        if (this.connecting !== null) {
            return this.connecting;
        }

        this.connecting = new Promise((resolve, reject) => {
            const socket = new WebSocket(this.url);
            this.socket = socket;

            socket.addEventListener("open", () => resolve());
            socket.addEventListener("error", () =>
                reject(new Error(`websocket connection failed: ${this.url}`)),
            );
            socket.addEventListener("message", (event: MessageEvent) =>
                this.receive(event),
            );
            socket.addEventListener("close", () => this.close());
        });

        return this.connecting;
    }

    async send(contract: Contract): Promise<unknown> {
        await this.connect();

        const socket = this.socket;
        if (socket === null) {
            throw new Error("connector is not connected");
        }

        const result = new Promise<unknown>((resolve, reject) => {
            this.pending.push({ resolve, reject });
        });

        socket.send(JSON.stringify(contract));
        return result;
    }

    onUpdate(listener: (update: ContractUpdate) => void): () => void {
        this.updates.add(listener);

        return () => {
            this.updates.delete(listener);
        };
    }

    private receive(event: MessageEvent): void {
        const message = JSON.parse(String(event.data)) as
            ContractResolution | ContractUpdate;

        if ("event" in message) {
            for (const listener of this.updates) {
                listener(message);
            }

            return;
        }

        const pending = this.pending.shift();

        if (pending === undefined) {
            return;
        }

        if (message.error !== null) {
            pending.reject(new Error(message.error));
            return;
        }

        pending.resolve(message.result);
    }

    private close(): void {
        this.connecting = null;
        this.socket = null;

        const pending = this.pending;
        this.pending = [];

        for (const request of pending) {
            request.reject(new Error("websocket closed"));
        }
    }
}

export const connector = new Connector();

export function configureConnector(options: ConnectorOptions): void {
    if (options.url !== undefined) {
        connector.url = options.url;
    }
}
