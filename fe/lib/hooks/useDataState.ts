import { UseQueryResult } from '@tanstack/react-query';

export function useDataState<TData>(
  queryResult: UseQueryResult<TData>,
  isEmptyFn?: (data: TData | undefined) => boolean
) {
  const { data, isLoading, isError, error } = queryResult;
  const isEmpty = !isLoading && !isError && (!data || (Array.isArray(data) && data.length === 0) || (isEmptyFn ? isEmptyFn(data) : false));
  return { data, isLoading, isEmpty, isError, error };
}