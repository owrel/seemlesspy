export type ContractKind =
    | "method"
    | "constructor"
    | "property"
    | "release"
    | "subscribe"
    | "unsubscribe";

export interface Contract {
    kind: ContractKind;
    cls_name: string;
    instance_id: string | null;
    member: string;
    params: [string, unknown][];
}

export interface ContractResolution {
    call: string;
    result: unknown;
    error: string | null;
}

export interface ContractUpdate {
    event: "update";
    instance_id: string;
    member: string;
    value: unknown;
}
