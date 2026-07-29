import { Data } from 'effect'

export class NetworkError extends Data.TaggedError('NetworkError')<{
  readonly status: number
  readonly message: string
}> {}

export class NotFoundError extends Data.TaggedError('NotFoundError')<{
  readonly id: string
}> {}
